// app/pages/Home.tsx
import { useState } from "react"
import { Download, Clock, MapPin } from "lucide-react"

import { NarrationPanel } from "@/components/explorer/NarrationPanel"
import { MapView } from "@/components/map/MapView"
import { LoadingOverlay } from "@/components/shared/LoadingOverlay"
import { RouteControls } from "@/components/shared/RouteControls"
import { RouteVariantPicker } from "@/components/shared/RouteVariantPicker"
import { BottomSheet, type SheetState } from "@/components/mobile/BottomSheet"
import { MobileRouteCards } from "@/components/mobile/MobileRouteCards"
import type { RouteResponse } from "@/types/route"
import { api, formatAxiosError } from "@/services/api"
import type { POI } from "@/types/poi"
import { useToast } from "@/components/ui/use-toast"

export function Home(): JSX.Element {
  const { toast } = useToast()

  // Route State
  const [routes, setRoutes] = useState<RouteResponse[]>([])
  const [activeRouteIdx, setActiveRouteIdx] = useState(0)
  const [isLoading, setIsLoading] = useState(false)

  // POI & Interaction State
  const [selectedPOI, setSelectedPOI] = useState<string | null>(null)
  const [showPOIs, setShowPOIs] = useState(false)
  const [isDiscovering, setIsDiscovering] = useState(false)

  // Cache stores POIs by route index: { 0: [poi1, poi2], 1: [poi3] }
  const [poiCache, setPoiCache] = useState<Record<number, POI[]>>({})

  // Mobile bottom sheet state
  const [sheetState, setSheetState] = useState<SheetState>("idle")

  const activeRoute = routes[activeRouteIdx] ?? null

  // ─────────────────────────────────────────────────────────────
  // Handlers
  // ─────────────────────────────────────────────────────────────

  const handleRoutesGenerated = (newRoutes: RouteResponse[]) => {
    setRoutes(newRoutes)
    setActiveRouteIdx(0)
    setSelectedPOI(null)
    setPoiCache({})
    setShowPOIs(false)
    // On mobile, snap sheet to route cards view after generation
    setSheetState("routes")
  }

  const handleSelectVariant = (idx: number) => {
    setActiveRouteIdx(idx)
    setSelectedPOI(null)
    setShowPOIs(false)
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

  const handleTogglePOIs = async () => {
    if (!activeRoute) return
    const nextState = !showPOIs
    setShowPOIs(nextState)

    if (nextState && !poiCache[activeRouteIdx]) {
      setIsDiscovering(true)
      try {
        const pois = await api.discoverPOIs({
          polyline: activeRoute.polyline,
          start_lng: activeRoute.polyline[0][0],
          start_lat: activeRoute.polyline[0][1],
          distance_km: activeRoute.distance_km,
        })
        setPoiCache(prev => ({ ...prev, [activeRouteIdx]: pois }))
        setRoutes(prev => {
          const newRoutes = [...prev]
          newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois }
          return newRoutes
        })
      } catch (err) {
        console.error("Failed to fetch POIs", err)
        setShowPOIs(false)
        toast({ title: "Discovery Failed", description: "Could not fetch local places.", variant: "destructive" })
      } finally {
        setIsDiscovering(false)
      }
    } else if (nextState && poiCache[activeRouteIdx]) {
      setRoutes(prev => {
        const newRoutes = [...prev]
        newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois: poiCache[activeRouteIdx] }
        return newRoutes
      })
    } else if (!nextState) {
      setRoutes(prev => {
        const newRoutes = [...prev]
        newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois: [] }
        return newRoutes
      })
      setSelectedPOI(null)
    }
  }

  const handleAddWaypoint = async (lng: number, lat: number) => {
    if (!activeRoute) return
    setIsLoading(true)

    const isLoop = activeRoute.source.includes('trip') || activeRoute.source.includes('loop')
    const isCycle = activeRoute.source.includes('driving') || activeRoute.source.includes('bike')
    const mode = isCycle ? 'cycle' : 'walk'
    const routeType = isLoop ? 'loop' : 'a2b'

    const startPt = activeRoute.polyline[0]
    const endPt = activeRoute.polyline[activeRoute.polyline.length - 1]

    try {
      const result = await api.generateRouteVariants({
        start_lng: startPt[0],
        start_lat: startPt[1],
        distance_km: activeRoute.distance_km,
        mode,
        routeType,
        end_lng: isLoop ? undefined : endPt[0],
        end_lat: isLoop ? undefined : endPt[1],
        waypoints: [[lng, lat]],
      })
      setRoutes(result.routes)
      setActiveRouteIdx(0)
      setSelectedPOI(null)
      setPoiCache({})
      setShowPOIs(false)
      toast({ title: "Route updated", description: "Your route now passes through this location." })
    } catch (e) {
      toast({ title: "Rerouting failed", description: "Could not map a path through that location.", variant: "destructive" })
    } finally {
      setIsLoading(false)
    }
  }

  const handleExport = async (): Promise<void> => {
    if (!activeRoute) return
    try {
      const blob = await api.exportGPX({
        polyline: activeRoute.polyline,
        pois: activeRoute.pois,
        route_name: "LoopWheeGo Route",
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "loopwheego_route.gpx"
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
          selectedPOI={selectedPOI}
          onSelectPOI={handleSelectPOI}
          onMapTap={handleMobileMapTap}
        />

        <LoadingOverlay visible={isLoading} />

        {/* FAB — shown when sheet is idle */}
        {sheetState === "idle" && !isLoading && (
          <button
            type="button"
            onClick={() => setSheetState("controls")}
            className="fab-enter absolute bottom-8 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-6 py-3.5 rounded-full font-semibold text-sm text-white"
            style={{
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
              isLoading={isLoading}
              setIsLoading={setIsLoading}
              hasRoutes={routes.length > 0}
            />
          </div>
          <div className={sheetState === "routes" ? "block" : "hidden"}>
            <MobileRouteCards
              routes={routes}
              activeIdx={activeRouteIdx}
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
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          hasRoutes={routes.length > 0}
        />

        {routes.length > 1 && !isLoading && (
          <div className="animate-fade-up">
            <RouteVariantPicker
              routes={routes}
              activeIdx={activeRouteIdx}
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
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{poiCache[activeRouteIdx]?.length || 0}</span> stops
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

        {/* DISCOVER PLACES TOGGLE */}
        {routes.length > 0 && !isLoading && (
          <div className="px-5 py-4" style={{ borderTop: "1px solid var(--border)" }}>
            <label
              htmlFor="poi-toggle"
              className="flex items-center justify-between cursor-pointer select-none group"
            >
              <div>
                <p className="text-[11px] uppercase tracking-widest font-semibold transition-colors group-hover:text-white" style={{ color: "var(--fg-faint)" }}>
                  Discover Places
                </p>
                <p className="text-[10px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
                  Find narrated landmarks along this path
                </p>
              </div>
              <div className="theme-switch">
                <input
                  type="checkbox"
                  id="poi-toggle"
                  checked={showPOIs}
                  onChange={handleTogglePOIs}
                  disabled={isDiscovering}
                />
                <div className="theme-switch-track" />
                <span className="theme-switch-thumb" />
              </div>
            </label>

            {isDiscovering && (
              <div className="text-xs flex items-center gap-2 mt-4" style={{ color: "var(--red)" }}>
                <span className="animate-spin w-3 h-3 border-2 border-current border-t-transparent rounded-full" />
                Consulting local AI guide... (approx 10s)
              </div>
            )}

            {showPOIs && !isDiscovering && poiCache[activeRouteIdx]?.length === 0 && (
              <p className="text-xs mt-4 italic" style={{ color: "var(--fg-muted)" }}>No notable places found on this specific path.</p>
            )}
          </div>
        )}

        {/* POI NARRATION PANEL */}
        {activeRoute && activeRoute.pois.length > 0 && showPOIs && !isLoading && !isDiscovering && (
          <div className="animate-fade-up">
            <NarrationPanel
              routeData={activeRoute}
              selectedPOI={selectedPOI}
              onSelectPOI={handleSelectPOI}
              onAddWaypoint={handleAddWaypoint}
            />
          </div>
        )}
      </aside>

      {/* MAP — desktop only (mobile has its own full-screen map above) */}
      <main className="hidden md:relative md:flex md:flex-1 md:overflow-hidden">
        <LoadingOverlay visible={isLoading} />
        <MapView
          routeData={activeRoute}
          selectedPOI={selectedPOI}
          onSelectPOI={handleSelectPOI}
        />
      </main>

    </div>
  )
}
