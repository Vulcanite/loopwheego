import { Loader2, MapPin, Navigation, Bike, Footprints, RotateCcw, ArrowRight, Plus, X, ChevronDown } from "lucide-react"
import { useState, useCallback, useEffect, useMemo, useRef } from "react"

import { PlaceSearch } from "@/components/shared/PlaceSearch"
import { Slider } from "@/components/ui/slider"
import { api, formatAxiosError } from "@/services/api"
import type { RouteRequest, RouteResponse } from "@/types/route"
import { useToast } from "@/components/ui/use-toast"
import { formatPOICategory } from "@/lib/poiPresentation"

interface RouteControlsProps {
  onRoutesGenerated: (routes: RouteResponse[], appMode: AppMode, session: RouteControlsSession) => void
  onLoopStopsPlanned: (stops: [number, number][]) => void
  onAppModeChange?: (mode: AppMode) => void
  onExplorerCategoriesChange?: (categories: string[]) => void
  onStartLocationChange?: (location: [number, number]) => void
  availableExplorerCategories?: string[]
  isLoading: boolean
  setIsLoading: (v: boolean) => void
  hasRoutes: boolean
}

type AppMode = "fitness" | "explorer"
type TransportMode = "walk" | "cycle"
type RouteType = "loop" | "a2b"
type StopDraft = {
  query: string
  lng: number | null
  lat: number | null
}
type RouteControlsSession = Pick<RouteRequest, "mode" | "routeType" | "distance_km" | "target_duration_minutes" | "poi_categories" | "waypoints"> & {
  appMode: AppMode
}

const MAX_WALK_KM = 50
const MAX_CYCLE_KM = 100
const MIN_DISTANCE_KM = 3
const MAX_WALK_DURATION = 300
const MAX_CYCLE_DURATION = 360
const SG_CENTER = { lng: 103.8198, lat: 1.3521, label: "Singapore City Centre" }
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
const SG_BOUNDS = {
  minLng: 103.60,
  maxLng: 104.05,
  minLat: 1.13,
  maxLat: 1.48,
}

function isWithinSingaporeBounds(lat: number, lng: number): boolean {
  return (
    lng >= SG_BOUNDS.minLng &&
    lng <= SG_BOUNDS.maxLng &&
    lat >= SG_BOUNDS.minLat &&
    lat <= SG_BOUNDS.maxLat
  )
}

function SectionLabel({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <p className="text-[11px] uppercase tracking-widest font-semibold mb-2" style={{ color: "var(--fg-faint)" }}>
      {children}
    </p>
  )
}

function TransportBtn({ active, icon: Icon, label, onClick, disabled }: {
  active: boolean; icon: React.ElementType; label: string; onClick: () => void; disabled: boolean
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
      style={{
        background: active ? "var(--red)" : "transparent",
        borderColor: active ? "var(--red)" : "var(--border-mid)",
        color: active ? "#fff" : "var(--fg-muted)",
      }}
    >
      <Icon size={15} />
      {label}
    </button>
  )
}

export function RouteControls({
  onRoutesGenerated,
  onLoopStopsPlanned,
  onAppModeChange,
  onExplorerCategoriesChange,
  onStartLocationChange,
  availableExplorerCategories,
  isLoading,
  setIsLoading,
  hasRoutes,
}: RouteControlsProps): JSX.Element {
  const { toast } = useToast()
  const disabled = isLoading

  const [appMode, setAppMode] = useState<AppMode>("fitness")
  const [transport, setTransport] = useState<TransportMode>("walk")
  const [routeType, setRouteType] = useState<RouteType>("loop")

  const [startLng, setStartLng] = useState<number | null>(null)
  const [startLat, setStartLat] = useState<number | null>(null)
  const [startLabel, setStartLabel] = useState("Detecting current location…")
  const [endLng, setEndLng] = useState<number | null>(null)
  const [endLat, setEndLat] = useState<number | null>(null)
  const [endLabel, setEndLabel] = useState("")
  const [gpsLoading, setGpsLoading] = useState(false)
  const [outsideSingapore, setOutsideSingapore] = useState(false)
  const [showRegionModal, setShowRegionModal] = useState(false)

  const [distanceKm, setDistanceKm] = useState(MIN_DISTANCE_KM)
  const [durationMin, setDurationMin] = useState(60)
  const [stops, setStops] = useState<StopDraft[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [isCategoryPickerOpen, setIsCategoryPickerOpen] = useState(false)
  const categoryPickerRef = useRef<HTMLDivElement | null>(null)
  const availableCategories = useMemo(
    () => (availableExplorerCategories && availableExplorerCategories.length > 0
      ? availableExplorerCategories
      : EXPLORER_CATEGORY_OPTIONS),
    [availableExplorerCategories]
  )
  const maxKm = transport === "walk" ? MAX_WALK_KM : MAX_CYCLE_KM
  const maxDuration = transport === "walk" ? MAX_WALK_DURATION : MAX_CYCLE_DURATION

  useEffect(() => {
    if (!navigator.geolocation) {
      setStartLat(SG_CENTER.lat)
      setStartLng(SG_CENTER.lng)
      setStartLabel(SG_CENTER.label)
      onStartLocationChange?.([SG_CENTER.lng, SG_CENTER.lat])
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        if (isWithinSingaporeBounds(latitude, longitude)) {
          setStartLat(latitude)
          setStartLng(longitude)
          setStartLabel(`My Location (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`)
          setOutsideSingapore(false)
          onStartLocationChange?.([longitude, latitude])
          return
        }
        setOutsideSingapore(true)
        setShowRegionModal(true)
        setStartLat(SG_CENTER.lat)
        setStartLng(SG_CENTER.lng)
        setStartLabel(SG_CENTER.label)
        onStartLocationChange?.([SG_CENTER.lng, SG_CENTER.lat])
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStartLat(SG_CENTER.lat)
          setStartLng(SG_CENTER.lng)
          setStartLabel(SG_CENTER.label)
          onStartLocationChange?.([SG_CENTER.lng, SG_CENTER.lat])
        }
      },
      { timeout: 8000 }
    )
  }, [onStartLocationChange])

  useEffect(() => {
    if (appMode !== "explorer") return
    onExplorerCategoriesChange?.(selectedCategories)
  }, [appMode, onExplorerCategoriesChange, selectedCategories])

  useEffect(() => {
    if (!isCategoryPickerOpen) return

    const handlePointerDown = (event: MouseEvent): void => {
      if (!categoryPickerRef.current?.contains(event.target as Node)) {
        setIsCategoryPickerOpen(false)
      }
    }

    const handleEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setIsCategoryPickerOpen(false)
    }

    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [isCategoryPickerOpen])

  useEffect(() => {
    setSelectedCategories((prev) => prev.filter((category) => availableCategories.includes(category)))
  }, [availableCategories])

  const handleGPS = useCallback(async () => {
    if (!navigator.geolocation) {
      toast({ title: "GPS unavailable", description: "Your browser doesn't support geolocation.", variant: "destructive" })
      return
    }
    if (outsideSingapore) return
    setGpsLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        if (!isWithinSingaporeBounds(latitude, longitude)) {
          setOutsideSingapore(true)
          setShowRegionModal(true)
          setStartLat(SG_CENTER.lat)
          setStartLng(SG_CENTER.lng)
          setStartLabel(SG_CENTER.label)
          onStartLocationChange?.([SG_CENTER.lng, SG_CENTER.lat])
          setGpsLoading(false)
          return
        }
        setStartLat(latitude)
        setStartLng(longitude)
        setStartLabel(`My Location (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`)
        setOutsideSingapore(false)
        onStartLocationChange?.([longitude, latitude])
        setGpsLoading(false)
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStartLat(SG_CENTER.lat)
          setStartLng(SG_CENTER.lng)
          setStartLabel(SG_CENTER.label)
          onStartLocationChange?.([SG_CENTER.lng, SG_CENTER.lat])
        }
        toast({ title: "Location denied", description: "Using Singapore City Centre as start point.", variant: "destructive" })
        setGpsLoading(false)
      },
      { timeout: 8000 }
    )
  }, [onStartLocationChange, outsideSingapore, toast])

  const handleGenerate = async (): Promise<void> => {
    if (startLng == null || startLat == null) {
      toast({ title: "Choose a start point", description: "Search or use GPS to set your location.", variant: "destructive" })
      return
    }
    if (routeType === "a2b" && (endLng == null || endLat == null)) {
      toast({ title: "Choose an end point", description: "For A→B routes, set a destination.", variant: "destructive" })
      return
    }
    if (routeType === "loop" && stops.some((stop) => stop.lng == null || stop.lat == null)) {
      toast({ title: "Finish your stops", description: "Select each stop from search results or remove unfinished stops.", variant: "destructive" })
      return
    }
    if (appMode === "explorer" && selectedCategories.length === 0) {
      toast({ title: "Choose categories", description: "Select at least one Explorer category.", variant: "destructive" })
      return
    }
    setIsLoading(true)
    try {
      const selectedStops = routeType === "loop" && stops.length > 0
        ? stops.map((stop) => [stop.lng as number, stop.lat as number] as [number, number])
        : []
      const explorerCategories = appMode === "explorer"
        ? selectedCategories
        : undefined
      const session: RouteControlsSession = {
        appMode,
        mode: transport,
        routeType,
        distance_km: appMode === "fitness" && routeType === "loop" ? distanceKm : undefined,
        target_duration_minutes: appMode === "explorer" ? durationMin : undefined,
        poi_categories: explorerCategories,
        waypoints: selectedStops.length > 0 ? selectedStops : undefined,
      }
      const result = await api.generateRouteVariants({
        start_lng: startLng,
        start_lat: startLat,
        distance_km: session.distance_km,
        target_duration_minutes: session.target_duration_minutes,
        appMode: session.appMode,
        mode: session.mode,
        routeType: session.routeType,
        end_lng: endLng,
        end_lat: endLat,
        waypoints: session.waypoints,
        poi_categories: session.poi_categories,
      })
      onLoopStopsPlanned(routeType === "loop" ? selectedStops : [])
      onRoutesGenerated(result.routes, appMode, session)
    } catch (e) {
      toast({ title: "Could not generate route", description: formatAxiosError(e), variant: "destructive" })
    } finally {
      setIsLoading(false)
    }
  }

  const toggleCategory = (category: string): void => {
    setSelectedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((value) => value !== category)
        : [...prev, category]
    )
  }

  const handleAddStop = (): void => {
    if (stops.length >= 3) return
    setStops((prev) => [...prev, { query: "", lng: null, lat: null }])
  }

  const handleRemoveStop = (idx: number): void => {
    setStops((prev) => prev.filter((_, currentIdx) => currentIdx !== idx))
  }

  const handleStopQueryChange = (idx: number, query: string): void => {
    setStops((prev) =>
      prev.map((stop, currentIdx) =>
        currentIdx === idx
          ? { query, lng: null, lat: null }
          : stop
      )
    )
  }

  const handleStopSelected = (idx: number, lng: number, lat: number, label: string): void => {
    setStops((prev) =>
      prev.map((stop, currentIdx) =>
        currentIdx === idx
          ? { query: label, lng, lat }
          : stop
      )
    )
  }

  return (
    <div className="relative z-20 flex flex-col p-5 pb-4 gap-0">

      {/* MODE TOGGLE */}
      <div className="flex gap-2 mb-4">
        {(["fitness", "explorer"] as AppMode[]).map((m) => (
          <button
            key={m}
            type="button"
            disabled={disabled}
            onClick={() => {
              if (m === appMode) return
              setAppMode(m)
              setStops([])
              if (m !== "explorer") setIsCategoryPickerOpen(false)
              onAppModeChange?.(m)
            }}
            className={`mode-tab border disabled:opacity-40 disabled:cursor-not-allowed`}
            style={{
              background: appMode === m ? "var(--red)" : "transparent",
              color: appMode === m ? "#fff" : "var(--fg-muted)",
              borderColor: appMode === m ? "var(--red)" : "var(--border-mid)",
            }}
          >
            {m === "fitness" ? "⚡ Fitness" : "🗺 Explorer"}
          </button>
        ))}
      </div>

      {/* TRANSPORT */}
      <div className="mb-4">
        <SectionLabel>Transport</SectionLabel>
        <div className="flex gap-2">
          <TransportBtn active={transport === "walk"} icon={Footprints} label="Walk" disabled={disabled}
            onClick={() => { setTransport("walk"); setDistanceKm(Math.max(MIN_DISTANCE_KM, Math.min(distanceKm, MAX_WALK_KM))) }} />
          <TransportBtn active={transport === "cycle"} icon={Bike} label="Cycle" disabled={disabled}
            onClick={() => { setTransport("cycle"); setDistanceKm(Math.max(MIN_DISTANCE_KM, Math.min(distanceKm, MAX_CYCLE_KM))) }} />
        </div>
      </div>

      {appMode === "explorer" && (
        <div className="mb-4 animate-fade-up">
          <div className="flex items-center justify-between mb-2">
            <SectionLabel>Categories</SectionLabel>
            <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>
              {selectedCategories.length > 0 ? `${selectedCategories.length} selected` : "None selected"}
            </span>
          </div>
          <div className="relative" ref={categoryPickerRef}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => setIsCategoryPickerOpen((prev) => !prev)}
              className="w-full rounded-xl border px-3 py-3 text-left transition-all disabled:opacity-40"
              style={{ borderColor: "var(--border-mid)", background: "var(--card)", color: "var(--fg)" }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 flex-wrap gap-2">
                  {selectedCategories.length > 0 ? (
                    selectedCategories.map((category) => (
                      <span
                        key={category}
                        className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium"
                        style={{ background: "rgba(230,51,41,0.12)", color: "var(--fg)" }}
                      >
                        {formatPOICategory(category)}
                      </span>
                    ))
                  ) : (
                    <span className="text-sm" style={{ color: "var(--fg-faint)" }}>
                      Select categories
                    </span>
                  )}
                </div>
                <ChevronDown
                  size={16}
                  style={{
                    color: "var(--fg-faint)",
                    transform: isCategoryPickerOpen ? "rotate(180deg)" : "rotate(0deg)",
                    transition: "transform 160ms ease",
                  }}
                />
              </div>
            </button>

            {isCategoryPickerOpen && (
              <div
                className="absolute left-0 right-0 top-[calc(100%+8px)] z-30 rounded-2xl border p-3 shadow-2xl"
                style={{ borderColor: "var(--border-mid)", background: "var(--surface)" }}
              >
                <div className="flex items-center justify-between mb-3">
                  <p className="text-[11px] uppercase tracking-widest font-semibold" style={{ color: "var(--fg-faint)" }}>
                    Explorer Categories
                  </p>
                  {selectedCategories.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedCategories([])}
                      className="text-[11px] transition-colors"
                      style={{ color: "var(--red)" }}
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {availableCategories.map((category) => {
                    const active = selectedCategories.includes(category)
                    return (
                      <button
                        key={category}
                        type="button"
                        disabled={disabled}
                        onClick={() => toggleCategory(category)}
                        className="rounded-full border px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-40"
                        style={{
                          background: active ? "var(--red)" : "transparent",
                          borderColor: active ? "var(--red)" : "var(--border-mid)",
                          color: active ? "#fff" : "var(--fg-muted)",
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
          <p className="text-[11px] mt-2" style={{ color: "var(--fg-faint)" }}>
            Explorer categories are opt-in. Select one or more before generating a route.
          </p>
        </div>
      )}

      {/* ROUTE TYPE */}
      <div className="mb-5">
        <SectionLabel>Route Type</SectionLabel>
        <div className="flex gap-2">
          {([["loop", "Loop", RotateCcw], ["a2b", "A → B", ArrowRight]] as const).map(([val, lbl, Icon]) => (
            <button
              key={val}
              type="button"
              disabled={disabled}
              onClick={() => setRouteType(val)}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: routeType === val ? "var(--red)" : "transparent",
                borderColor: routeType === val ? "var(--red)" : "var(--border-mid)",
                color: routeType === val ? "#fff" : "var(--fg-muted)",
              }}
            >
              <Icon size={15} />
              {lbl}
            </button>
          ))}
        </div>
      </div>

      {/* START */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <SectionLabel>Start Point</SectionLabel>
          {!outsideSingapore && (
            <button
              type="button"
              onClick={() => void handleGPS()}
              disabled={gpsLoading || disabled}
              className="flex items-center gap-1 text-[11px] transition-colors disabled:opacity-40"
              style={{ color: "var(--red)" }}
            >
              {gpsLoading ? <Loader2 size={11} className="animate-spin" /> : <Navigation size={11} />}
              Use GPS
            </button>
          )}
        </div>
        <PlaceSearch
          query={startLabel}
          onQueryChange={setStartLabel}
          disabled={disabled}
          onPlaceSelected={(lng, lat, label) => {
            setStartLng(lng)
            setStartLat(lat)
            setStartLabel(label)
            onStartLocationChange?.([lng, lat])
          }}
          placeholder="Search address or place…"
        />
      </div>

      {/* END (A→B only) */}
      {routeType === "a2b" && (
        <div className="mb-4 animate-fade-up">
          <SectionLabel>End Point</SectionLabel>
          <PlaceSearch
            query={endLabel}
            onQueryChange={setEndLabel}
            disabled={disabled}
            onPlaceSelected={(lng, lat, label) => { setEndLng(lng); setEndLat(lat); setEndLabel(label) }}
            placeholder="Search destination…"
          />
        </div>
      )}

      {routeType === "loop" && (
        <div className="mb-4 animate-fade-up">
          <div className="flex items-center justify-between mb-2">
            <SectionLabel>Stops</SectionLabel>
            <button
              type="button"
              onClick={handleAddStop}
              disabled={disabled || stops.length >= 3}
              className="flex items-center gap-1 text-[11px] transition-colors disabled:opacity-40"
              style={{ color: "var(--red)" }}
            >
              <Plus size={11} />
              Add Stop
            </button>
          </div>

          {stops.length === 0 ? (
            <p className="text-xs leading-relaxed" style={{ color: "var(--fg-faint)" }}>
              Add up to 3 stops before generating a loop route.
            </p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {stops.map((stop, idx) => (
                <div key={idx} className="rounded-xl p-3" style={{ background: "var(--card)", border: "1px solid var(--border-mid)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] uppercase tracking-widest font-semibold" style={{ color: "var(--fg-faint)" }}>
                      Stop {idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleRemoveStop(idx)}
                      disabled={disabled}
                      className="flex items-center gap-1 text-[11px] transition-colors disabled:opacity-40"
                      style={{ color: "var(--fg-muted)" }}
                    >
                      <X size={11} />
                      Remove
                    </button>
                  </div>
                  <PlaceSearch
                    query={stop.query}
                    onQueryChange={(query) => handleStopQueryChange(idx, query)}
                    onPlaceSelected={(lng, lat, label) => handleStopSelected(idx, lng, lat, label)}
                    placeholder="Search stop..."
                    disabled={disabled}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* DISTANCE (Fitness only) */}
      {routeType === "loop" && appMode === "fitness" && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <SectionLabel>Distance</SectionLabel>
            <span className="text-sm font-semibold tabular-nums" style={{ color: "var(--fg)" }}>
              {distanceKm.toFixed(1)} km
            </span>
          </div>
          <Slider min={MIN_DISTANCE_KM} max={maxKm} step={0.5} value={[distanceKm]} disabled={disabled}
            onValueChange={(v) => { const val = v[0]; if (val !== undefined) setDistanceKm(val) }} />
          <div className="flex justify-between mt-1 text-[10px]" style={{ color: "var(--fg-faint)" }}>
            <span>{MIN_DISTANCE_KM} km</span><span>{maxKm} km</span>
          </div>
        </div>
      )}

      {/* DURATION (Explorer only) */}
      {appMode === "explorer" && (
        <div className="mb-4 animate-fade-up">
          <div className="flex items-center justify-between mb-2">
            <SectionLabel>Duration</SectionLabel>
            <span className="text-sm font-semibold tabular-nums" style={{ color: "var(--fg)" }}>
              {durationMin >= 60 ? `${Math.floor(durationMin / 60)}h${durationMin % 60 ? ` ${durationMin % 60}m` : ""}` : `${durationMin}m`}
            </span>
          </div>
          <div className="animate-fade-up">
            <Slider min={15} max={maxDuration} step={15} value={[durationMin]} disabled={disabled}
              onValueChange={(v) => { const val = v[0]; if (val !== undefined) setDurationMin(val) }} />
            <div className="flex justify-between mt-1 text-[10px]" style={{ color: "var(--fg-faint)" }}>
              <span>15 min</span><span>{Math.floor(maxDuration / 60)} hr</span>
            </div>
          </div>
        </div>
      )}

      {/* GENERATE */}
      <button
        type="button"
        disabled={isLoading}
        onClick={() => void handleGenerate()}
        className="w-full py-3 rounded-xl font-semibold text-sm text-white transition-all duration-200 mb-5 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
        style={{
          background: isLoading ? "color-mix(in srgb, var(--red) 50%, transparent)" : "var(--red)",
          boxShadow: isLoading ? "none" : "0 4px 20px var(--red-glow)",
        }}
      >
        {isLoading
          ? <><Loader2 size={16} className="animate-spin" />Generating…</>
          : <><MapPin size={16} />{hasRoutes ? "Regenerate Routes" : "Generate Routes"}</>
        }
      </button>

      {showRegionModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.45)" }}
          onClick={() => setShowRegionModal(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl p-5 border text-center"
            style={{ background: "var(--surface)", borderColor: "var(--border-mid)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm leading-relaxed" style={{ color: "var(--fg)" }}>
              LoopWheeGo currently supports Singapore only.
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--fg-faint)" }}>
              LoopWheeGo is our launchpad in Singapore, where we are tuning every route for real walkers and riders.
              We will be bringing it to other regions soon.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
