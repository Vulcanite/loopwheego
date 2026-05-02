// app/pages/Home.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Download, Clock, MapPin, ChevronDown } from "lucide-react"

import { NarrationPanel } from "@/components/explorer/NarrationPanel"
import { MapView } from "@/components/map/MapView"
import { LoadingOverlay } from "@/components/shared/LoadingOverlay"
import { RouteControls } from "@/components/shared/RouteControls"
import { RouteVariantPicker } from "@/components/shared/RouteVariantPicker"
import { BottomSheet, type SheetState } from "@/components/mobile/BottomSheet"
import { MobileRouteCards } from "@/components/mobile/MobileRouteCards"
import type { AppMode, RouteResponse, RouteType, TransportMode } from "@/types/route"
import { api, formatAxiosError } from "@/services/api"
import { useToast } from "@/components/ui/use-toast"
import type { POI } from "@/types/poi"
import type { SuggestedPlace } from "@/types/place"
import { formatPOICategory } from "@/lib/poiPresentation"

type RouteSession = {
  appMode: AppMode
  mode: TransportMode
  routeType?: RouteType
  distance_km?: number
  target_duration_minutes?: number
  poi_categories?: string[]
  waypoints?: [number, number][]
  start_lng: number
  start_lat: number
  end_lng?: number | null
  end_lat?: number | null
}

const EXPLORER_CATEGORY_OPTIONS = [
  "parks",
  "nature",
  "waterfront",
  "monuments",
  "heritage",
  "museums",
  "viewpoints",
  "hawker_centres",
  "cafes",
  "arts",
]

export function Home(): JSX.Element {
  const { toast } = useToast()
  const isMountedRef = useRef(false)
  const explorerPlacesRequestRef = useRef<Promise<void> | null>(null)
  const [plannedStops, setPlannedStops] = useState<[number, number][]>([])
  const [startLocation, setStartLocation] = useState<[number, number] | null>(null)
  const [cachedExplorerPlaces, setCachedExplorerPlaces] = useState<SuggestedPlace[]>([])
  const [explorerPreviewCategories, setExplorerPreviewCategories] = useState<string[]>(["monuments"])
  const [isExplorerBrowseOpen, setIsExplorerBrowseOpen] = useState(false)
  const [selectedExplorerCategories, setSelectedExplorerCategories] = useState<string[]>([])
  const [explorerViewport, setExplorerViewport] = useState<{
    west: number
    south: number
    east: number
    north: number
    zoom: number
  } | null>(null)

  // Route State
  const [routes, setRoutes] = useState<RouteResponse[]>([])
  const [activeRouteIdx, setActiveRouteIdx] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [activeAppMode, setActiveAppMode] = useState<AppMode>("fitness")

  // POI & Interaction State
  const [selectedPOI, setSelectedPOI] = useState<string | null>(null)

  // Mobile bottom sheet state
  const [sheetState, setSheetState] = useState<SheetState>("idle")

  // Active session — stored for waypoint-add re-generation
  const [activeSession, setActiveSession] = useState<RouteSession | null>(null)
  const [addedPOIIds, setAddedPOIIds] = useState<Set<string>>(new Set())
  const [fitTrigger, setFitTrigger] = useState(0)


  const haversineMeters = (a: SuggestedPlace, b: SuggestedPlace): number => {
    const r = 6371000
    const p1 = (a.lat * Math.PI) / 180
    const p2 = (b.lat * Math.PI) / 180
    const dLat = ((b.lat - a.lat) * Math.PI) / 180
    const dLng = ((b.lng - a.lng) * Math.PI) / 180
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2
    return 2 * r * Math.asin(Math.min(1, Math.sqrt(h)))
  }

  const selectDistributedPlaces = (places: SuggestedPlace[], limit: number): SuggestedPlace[] => {
    if (places.length <= limit) return places
    const sorted = [...places].sort((a, b) => a.name.localeCompare(b.name))
    const selected: SuggestedPlace[] = [sorted[0]]
    let remaining = sorted.slice(1)

    while (selected.length < limit && remaining.length > 0) {
      let bestIdx = 0
      let bestScore = -1

      remaining.forEach((candidate, idx) => {
        const score = Math.min(...selected.map((picked) => haversineMeters(candidate, picked)))
        if (score > bestScore) {
          bestScore = score
          bestIdx = idx
        }
      })

      selected.push(remaining[bestIdx] as SuggestedPlace)
      remaining = remaining.filter((_, idx) => idx !== bestIdx)
    }

    return selected
  }

  const activeRoute = routes[activeRouteIdx] ?? null
  const availableExplorerCategories = useMemo(
    () => {
      if (cachedExplorerPlaces.length === 0) return EXPLORER_CATEGORY_OPTIONS
      const categorySet = new Set(cachedExplorerPlaces.map((place) => place.category))
      return EXPLORER_CATEGORY_OPTIONS.filter((category) => categorySet.has(category))
    },
    [cachedExplorerPlaces]
  )
  const explorerMapCategories = useMemo(
    () => {
      const available = availableExplorerCategories
      if (selectedExplorerCategories.length === 0) return available
      return available.filter((category) => selectedExplorerCategories.includes(category))
    },
    [availableExplorerCategories, selectedExplorerCategories]
  )
  const explorerPreviewPOIs = useMemo<POI[]>(() => {
    if (activeAppMode !== "explorer" || activeRoute) return []
    if (explorerPreviewCategories.length === 0) return []
    const viewportPlaces = cachedExplorerPlaces.filter((place) => {
      if (!explorerPreviewCategories.includes(place.category)) return false
      if (!explorerViewport) return true
      return (
        place.lng >= explorerViewport.west &&
        place.lng <= explorerViewport.east &&
        place.lat >= explorerViewport.south &&
        place.lat <= explorerViewport.north
      )
    })
    const allCandidatePlaces = cachedExplorerPlaces.filter((place) => explorerPreviewCategories.includes(place.category))
    const sourcePlaces = viewportPlaces.length > 0 ? viewportPlaces : allCandidatePlaces
    const zoom = explorerViewport?.zoom ?? 11.5
    const cap = zoom < 11.5 ? 18 : zoom < 12.5 ? 30 : zoom < 13.5 ? 45 : 70
    const visiblePlaces = selectDistributedPlaces(sourcePlaces, cap)
    return visiblePlaces.map((place) => ({
      id: place.id,
      name: place.name,
      lat: place.lat,
      lng: place.lng,
      category: place.category,
      narration: place.description,
      duration_suggested_minutes: 15,
    }))
  }, [activeAppMode, activeRoute, cachedExplorerPlaces, explorerPreviewCategories, explorerViewport])
  const mobileFitPadding = useMemo(() => (
    sheetState === "controls"
      ? { top: 92, right: 28, bottom: 380, left: 28 }
      : sheetState === "routes"
        ? { top: 92, right: 28, bottom: 250, left: 28 }
        : { top: 92, right: 28, bottom: 120, left: 28 }
  ), [sheetState])

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (activeAppMode !== "explorer") return
    if (cachedExplorerPlaces.length > 0) return
    if (explorerPlacesRequestRef.current) return

    explorerPlacesRequestRef.current = api.getSuggestedPlaces()
      .then((places) => {
        if (!isMountedRef.current) return
        setCachedExplorerPlaces(places)
        const categories = Array.from(new Set(places.map((place) => place.category)))
        if (categories.includes("monuments")) {
          setExplorerPreviewCategories(["monuments"])
        } else if (categories.length > 0 && categories[0]) {
          setExplorerPreviewCategories([categories[0]])
        }
      })
      .catch(() => {
        if (!isMountedRef.current) return
        setCachedExplorerPlaces([])
      })
      .finally(() => {
        explorerPlacesRequestRef.current = null
      })
  }, [activeAppMode, cachedExplorerPlaces.length])

  // ─────────────────────────────────────────────────────────────
  // Handlers
  // ─────────────────────────────────────────────────────────────

  const resetRouteState = (nextMode: AppMode) => {
    setRoutes([])
    setActiveRouteIdx(0)
    setSelectedPOI(null)
    setPlannedStops([])
    setActiveAppMode(nextMode)
    setIsExplorerBrowseOpen(false)
    setExplorerViewport(null)
    setSheetState("controls")
  }

  const handleRoutesGenerated = (newRoutes: RouteResponse[], appMode: AppMode, session?: RouteSession) => {
    setRoutes(newRoutes)
    setActiveAppMode(appMode)
    setPlannedStops(session?.waypoints ?? [])
    setActiveRouteIdx(0)
    setSelectedPOI(null)
    setActiveSession(session ?? null)
    setAddedPOIIds(new Set())
    setSheetState("routes")
  }

  const handleAddWaypointToRoute = useCallback(async (lng: number, lat: number, poiId: string): Promise<void> => {
    if (!activeSession || activeAppMode !== "explorer") return
    const newWaypoints: [number, number][] = [...(activeSession.waypoints ?? []), [lng, lat]]
    const updatedSession: RouteSession = { ...activeSession, waypoints: newWaypoints }
    setIsLoading(true)
    try {
      const result = await api.generateRouteVariants({
        start_lng: updatedSession.start_lng,
        start_lat: updatedSession.start_lat,
        end_lng: updatedSession.end_lng,
        end_lat: updatedSession.end_lat,
        appMode: updatedSession.appMode,
        mode: updatedSession.mode,
        routeType: updatedSession.routeType,
        distance_km: updatedSession.distance_km,
        target_duration_minutes: updatedSession.target_duration_minutes,
        poi_categories: updatedSession.poi_categories,
        waypoints: newWaypoints,
        max_routes: 1,
      })
      if (result.routes.length === 0) {
        toast({ title: "Could not add stop", description: "No route found through that point.", variant: "destructive" })
        return
      }
      setRoutes(result.routes)
      setActiveRouteIdx(0)
      setSelectedPOI(null)
      setPlannedStops(newWaypoints)
      setActiveSession(updatedSession)
      setAddedPOIIds((prev) => new Set([...prev, poiId]))
    } catch (e) {
      toast({ title: "Could not add stop", description: formatAxiosError(e), variant: "destructive" })
    } finally {
      setIsLoading(false)
    }
  }, [activeSession, activeAppMode, toast])

  const handleAppModeChange = useCallback((mode: AppMode) => {
    if (mode === activeAppMode) return
    resetRouteState(mode)
  }, [activeAppMode])

  const handleExplorerCategoriesChange = useCallback((categories: string[]) => {
    setSelectedExplorerCategories(categories)
  }, [])

  const toggleExplorerPreviewCategory = (category: string) => {
    setExplorerPreviewCategories((prev) => {
      if (prev.includes(category)) {
        return prev.filter((value) => value !== category)
      }
      if (prev.length >= 3) {
        return [...prev.slice(1), category]
      }
      return [...prev, category]
    })
  }

  const handleSelectVariant = (idx: number) => {
    setActiveRouteIdx(idx)
    setSelectedPOI(null)
  }

  const handleSelectPOI = (id: string) => {
    setSelectedPOI(prev => prev === id ? null : id)
  }

  // Handle sheet drag-handle tap: toggle between states
  const handleSheetHandleTap = () => {
    if (sheetState === "controls") {
      // If we have routes, snap back to route cards; otherwise close
      setSheetState(routes.length > 0 ? "routes" : "idle")
    } else if (sheetState === "routes") {
      setSheetState("controls")
    }
  }

  const handleMobileMapTap = () => {
    if (routes.length > 0 && sheetState !== "routes") {
      setSheetState("routes")
    }
  }

  const handleExport = async (): Promise<void> => {
    if (!activeRoute) return
    const routeNumber = activeRouteIdx + 1
    const filename = `loopwheego_route_${routeNumber}.gpx`
    try {
      const blob = await api.exportGPX({
        polyline: activeRoute.polyline,
        pois: activeRoute.pois,
        route_name: `LoopWheeGo Route ${routeNumber}`,
      })
      // No MIME type — iOS infers the UTI from the .gpx extension, which causes
      // it to surface all installed GPX-compatible apps in the share sheet.
      const file = new File([blob], filename)
      if (navigator.canShare?.({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: filename })
          return
        } catch (e) {
          if ((e as DOMException).name === "AbortError") return
          // share failed — fall through to plain download
        }
      }
      // Desktop / unsupported: plain download
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast({ title: "GPX export failed", description: formatAxiosError(e), variant: "destructive" })
    }
  }


  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────

  return (
    <div className="flex-1 flex overflow-hidden font-body">

      {/* ══════════════════════════════════════════
          MOBILE LAYOUT  (< md)
      ══════════════════════════════════════════ */}
      <div className="md:hidden relative flex-1">
        {/* Map — always full screen on mobile */}
        <MapView
          routeData={activeRoute}
          plannedStops={plannedStops}
          explorerPreviewPOIs={explorerPreviewPOIs}
          focusLocation={startLocation}
          onViewportChange={setExplorerViewport}
          selectedPOI={selectedPOI}
          onSelectPOI={handleSelectPOI}
          onMapTap={handleMobileMapTap}
          fitPadding={mobileFitPadding}
          fitTrigger={fitTrigger}
          onAddWaypoint={activeAppMode === "explorer" ? (lng, lat, poiId) => void handleAddWaypointToRoute(lng, lat, poiId) : undefined}
          addedPOIIds={addedPOIIds}
        />

        {activeAppMode === "explorer" && !activeRoute && explorerMapCategories.length > 0 && (
          <div className="absolute left-4 top-4 z-20">
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsExplorerBrowseOpen((prev) => !prev)}
                className="flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium backdrop-blur-md"
                style={{
                  background: "var(--map-float-bg)",
                  border: "1px solid var(--map-float-border)",
                  color: "var(--map-float-fg)",
                  boxShadow: "0 10px 30px rgba(0,0,0,0.12)",
                }}
              >
                Browse POIs
                <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: "var(--map-float-chip)" }}>
                  {explorerPreviewCategories.length > 0
                    ? explorerPreviewCategories.map((category) => formatPOICategory(category)).join(", ")
                    : "None"}
                </span>
                <ChevronDown size={14} style={{ transform: isExplorerBrowseOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 160ms ease" }} />
              </button>
              {isExplorerBrowseOpen && (
                <div
                  className="mt-2 w-[220px] rounded-2xl p-3 backdrop-blur-md"
                  style={{
                    background: "var(--map-float-panel-bg)",
                    border: "1px solid var(--map-float-border)",
                    boxShadow: "0 12px 36px rgba(0,0,0,0.14)",
                  }}
                >
                  <p className="mb-2 text-[11px] uppercase tracking-widest" style={{ color: "var(--map-float-muted)" }}>
                    Preview Categories
                  </p>
                  <p className="mb-3 text-[11px]" style={{ color: "var(--map-float-subtle)" }}>
                    Select up to three categories.
                  </p>
                  <div className="flex flex-col gap-2">
                    {explorerMapCategories.map((category) => {
                      const active = explorerPreviewCategories.includes(category)
                      return (
                        <button
                          key={category}
                          type="button"
                          onClick={() => toggleExplorerPreviewCategory(category)}
                          className="rounded-xl px-3 py-2 text-left text-sm transition-all"
                          style={{
                            background: active ? "var(--red)" : "var(--map-float-option-bg)",
                            color: active ? "#fff" : "var(--map-float-fg)",
                          }}
                        >
                          {formatPOICategory(category)}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <LoadingOverlay visible={isLoading} />

        {/* Zoom-out button — shown when zoomed past route level */}
        {activeRoute && !isLoading && (explorerViewport?.zoom ?? 0) > 14 && (
          <button
            type="button"
            onClick={() => setFitTrigger((n) => n + 1)}
            className="absolute right-4 z-20 flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-semibold backdrop-blur-sm animate-fade-up"
            style={{
              top: "calc(env(safe-area-inset-top, 0px) + 16px)",
              background: "var(--map-float-bg)",
              border: "1px solid var(--map-float-border)",
              color: "var(--map-float-fg)",
              boxShadow: "0 4px 20px rgba(0,0,0,0.18)",
            }}
          >
            <MapPin size={13} style={{ color: "var(--red)" }} />
            Show Route
          </button>
        )}

        {/* FAB — shown when sheet is idle */}
        {sheetState === "idle" && !isLoading && (
          <button
            type="button"
            onClick={() => setSheetState("controls")}
            className="fab-enter absolute left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-6 py-3.5 rounded-full font-semibold text-sm text-white"
            style={{
              bottom: "calc(env(safe-area-inset-bottom, 0px) + 16px)",
              background: "var(--red)",
              boxShadow: "0 4px 28px var(--red-glow)",
            }}
          >
            <MapPin size={16} />
            Plan a Route
          </button>
        )}

        {/* Bottom Sheet */}
        <BottomSheet state={sheetState} onHandleTap={handleSheetHandleTap}>
          <div className={sheetState === "routes" ? "hidden" : "block"}>
            <RouteControls
              onRoutesGenerated={handleRoutesGenerated}
              onLoopStopsPlanned={setPlannedStops}
              onAppModeChange={handleAppModeChange}
              onExplorerCategoriesChange={handleExplorerCategoriesChange}
              onStartLocationChange={setStartLocation}
              availableExplorerCategories={availableExplorerCategories}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              hasRoutes={routes.length > 0}
            />
          </div>
          <div className={sheetState === "routes" ? "block" : "hidden"}>
            <MobileRouteCards
              routes={routes}
              activeIdx={activeRouteIdx}
              appMode={activeAppMode}
              onSelect={handleSelectVariant}
              onExport={() => void handleExport()}
            />
          </div>
        </BottomSheet>
      </div>

      {/* ══════════════════════════════════════════
          DESKTOP LAYOUT  (≥ md)
      ══════════════════════════════════════════ */}
      <aside
        className="hidden md:flex w-[380px] shrink-0 flex-col overflow-y-auto"
        style={{ background: "var(--surface)", borderRight: "1px solid var(--sidebar-border)", zIndex: 10 }}
      >
        <RouteControls
          onRoutesGenerated={handleRoutesGenerated}
          onLoopStopsPlanned={setPlannedStops}
          onAppModeChange={handleAppModeChange}
          onExplorerCategoriesChange={handleExplorerCategoriesChange}
          onStartLocationChange={setStartLocation}
          availableExplorerCategories={availableExplorerCategories}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          hasRoutes={routes.length > 0}
        />

        {routes.length > 0 && !isLoading && (
          <div className="relative z-10 animate-fade-up">
            <RouteVariantPicker
              routes={routes}
              activeIdx={activeRouteIdx}
              appMode={activeAppMode}
              onSelect={handleSelectVariant}
            />
          </div>
        )}

        {/* STATS BAR */}
        {activeRoute && !isLoading && (
          <div className="px-5 py-3 flex items-center gap-4 animate-fade-up" style={{ background: "var(--scrim)", borderTop: "1px solid var(--border)" }}>
            <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-muted)" }}>
              <MapPin size={12} style={{ color: "var(--red)" }} />
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{activeRoute.distance_km.toFixed(1)}</span> km
            </div>
            <div className="w-px h-3" style={{ background: "var(--border-mid)" }} />
            <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-muted)" }}>
              <Clock size={12} style={{ color: "var(--red)" }} />
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{activeRoute.duration_minutes}</span> min
            </div>
            <div className="w-px h-3" style={{ background: "var(--border-mid)" }} />
            <div className="text-xs" style={{ color: "var(--fg-muted)" }}>
              <span className="font-semibold" style={{ color: "var(--fg)" }}>
                {activeAppMode === "explorer" ? activeRoute.pois.length : plannedStops.length}
              </span> {activeAppMode === "explorer" ? "POIs" : "stops"}
            </div>
            <button
              type="button"
              onClick={() => void handleExport()}
              className="ml-auto flex items-center gap-1.5 text-xs transition-colors py-1 px-2 rounded-md"
              style={{ color: "var(--fg-faint)" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--fg)"; (e.currentTarget as HTMLElement).style.background = "var(--pill-hover)" }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--fg-faint)"; (e.currentTarget as HTMLElement).style.background = "transparent" }}
            >
              <Download size={12} /> GPX
            </button>
          </div>
        )}

        {/* POI NARRATION PANEL */}
        {activeRoute && activeRoute.pois.length > 0 && activeAppMode === "explorer" && !isLoading && (
          <div className="animate-fade-up">
            <NarrationPanel
              routeData={activeRoute}
              selectedPOI={selectedPOI}
              onSelectPOI={handleSelectPOI}
              onAddWaypoint={(lng, lat, poiId) => void handleAddWaypointToRoute(lng, lat, poiId)}
              addedPOIIds={addedPOIIds}
            />
          </div>
        )}
      </aside>

      {/* MAP — desktop only (mobile has its own full-screen map above) */}
      <main className="hidden md:relative md:flex md:flex-1 md:overflow-hidden">
        <LoadingOverlay visible={isLoading} />
        {activeAppMode === "explorer" && !activeRoute && explorerMapCategories.length > 0 && (
          <div className="absolute left-5 top-5 z-20">
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsExplorerBrowseOpen((prev) => !prev)}
                className="flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium backdrop-blur-md"
                style={{
                  background: "var(--map-float-bg)",
                  border: "1px solid var(--map-float-border)",
                  color: "var(--map-float-fg)",
                  boxShadow: "0 10px 30px rgba(0,0,0,0.12)",
                }}
              >
                Browse POIs
                <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ background: "var(--map-float-chip)" }}>
                  {explorerPreviewCategories.length > 0
                    ? explorerPreviewCategories.map((category) => formatPOICategory(category)).join(", ")
                    : "None"}
                </span>
                <ChevronDown size={14} style={{ transform: isExplorerBrowseOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 160ms ease" }} />
              </button>
              {isExplorerBrowseOpen && (
                <div
                  className="mt-2 w-[240px] rounded-2xl p-3 backdrop-blur-md"
                  style={{
                    background: "var(--map-float-panel-bg)",
                    border: "1px solid var(--map-float-border)",
                    boxShadow: "0 12px 36px rgba(0,0,0,0.14)",
                  }}
                >
                  <p className="mb-2 text-[11px] uppercase tracking-widest" style={{ color: "var(--map-float-muted)" }}>
                    Preview Categories
                  </p>
                  <p className="mb-3 text-[11px]" style={{ color: "var(--map-float-subtle)" }}>
                    Select up to three categories.
                  </p>
                  <div className="flex flex-col gap-2">
                    {explorerMapCategories.map((category) => {
                      const active = explorerPreviewCategories.includes(category)
                      return (
                        <button
                          key={category}
                          type="button"
                          onClick={() => toggleExplorerPreviewCategory(category)}
                          className="rounded-xl px-3 py-2 text-left text-sm transition-all"
                          style={{
                            background: active ? "var(--red)" : "var(--map-float-option-bg)",
                            color: active ? "#fff" : "var(--map-float-fg)",
                          }}
                        >
                          {formatPOICategory(category)}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        <MapView
          routeData={activeRoute}
          plannedStops={plannedStops}
          explorerPreviewPOIs={explorerPreviewPOIs}
          focusLocation={startLocation}
          onViewportChange={setExplorerViewport}
          selectedPOI={selectedPOI}
          onSelectPOI={handleSelectPOI}
          onAddWaypoint={activeAppMode === "explorer" ? (lng, lat, poiId) => void handleAddWaypointToRoute(lng, lat, poiId) : undefined}
          addedPOIIds={addedPOIIds}
        />
      </main>


    </div>
  )
}
