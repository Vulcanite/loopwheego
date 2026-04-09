import { Loader2, MapPin, Navigation, Bike, Footprints, RotateCcw, ArrowRight } from "lucide-react"
import { useState, useCallback, useEffect } from "react"

import { PlaceSearch } from "@/components/shared/PlaceSearch"
import { Slider } from "@/components/ui/slider"
import { api, formatAxiosError } from "@/services/api"
import type { RouteResponse } from "@/types/route"
import { useToast } from "@/components/ui/use-toast"

interface RouteControlsProps {
  onRoutesGenerated: (routes: RouteResponse[]) => void
  isLoading: boolean
  setIsLoading: (v: boolean) => void
  hasRoutes: boolean
}

type AppMode = "fitness" | "explorer"
type TransportMode = "walk" | "cycle"
type RouteType = "loop" | "a2b"

const MAX_WALK_KM = 50
const MAX_CYCLE_KM = 100
const MAX_WALK_DURATION = 300
const MAX_CYCLE_DURATION = 360
const SG_CENTER = { lng: 103.8198, lat: 1.3521, label: "Singapore City Centre" }

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
  isLoading,
  setIsLoading,
  hasRoutes,
}: RouteControlsProps): JSX.Element {
  const { toast } = useToast()
  const token = import.meta.env.VITE_MAPBOX_TOKEN ?? ""
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

  const [distanceKm, setDistanceKm] = useState(5)
  const [durationMin, setDurationMin] = useState(60)
  const maxKm = transport === "walk" ? MAX_WALK_KM : MAX_CYCLE_KM
  const maxDuration = transport === "walk" ? MAX_WALK_DURATION : MAX_CYCLE_DURATION

  useEffect(() => {
    if (!navigator.geolocation) {
      setStartLat(SG_CENTER.lat)
      setStartLng(SG_CENTER.lng)
      setStartLabel(SG_CENTER.label)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        setStartLat(latitude)
        setStartLng(longitude)
        setStartLabel(`My Location (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`)
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStartLat(SG_CENTER.lat)
          setStartLng(SG_CENTER.lng)
          setStartLabel(SG_CENTER.label)
        }
      },
      { timeout: 8000 }
    )
  }, [])

  const handleGPS = useCallback(async () => {
    if (!navigator.geolocation) {
      toast({ title: "GPS unavailable", description: "Your browser doesn't support geolocation.", variant: "destructive" })
      return
    }
    setGpsLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        setStartLat(latitude)
        setStartLng(longitude)
        setStartLabel(`My Location (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`)
        setGpsLoading(false)
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStartLat(SG_CENTER.lat)
          setStartLng(SG_CENTER.lng)
          setStartLabel(SG_CENTER.label)
        }
        toast({ title: "Location denied", description: "Using Singapore City Centre as start point.", variant: "destructive" })
        setGpsLoading(false)
      },
      { timeout: 8000 }
    )
  }, [toast])

  const handleGenerate = async (): Promise<void> => {
    if (startLng == null || startLat == null) {
      toast({ title: "Choose a start point", description: "Search or use GPS to set your location.", variant: "destructive" })
      return
    }
    if (routeType === "a2b" && (endLng == null || endLat == null)) {
      toast({ title: "Choose an end point", description: "For A→B routes, set a destination.", variant: "destructive" })
      return
    }
    setIsLoading(true)
    try {
      const result = await api.generateRouteVariants({
        start_lng: startLng,
        start_lat: startLat,
        distance_km: appMode === "fitness" && routeType === "loop" ? distanceKm : undefined,
        target_duration_minutes: appMode === "explorer" && routeType === "loop" ? durationMin : undefined,
        appMode,
        mode: transport,
        routeType: routeType,
        end_lng: endLng,
        end_lat: endLat,
      })
      onRoutesGenerated(result.routes)
    } catch (e) {
      toast({ title: "Could not generate route", description: formatAxiosError(e), variant: "destructive" })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col p-5 pb-4 gap-0">

      {/* MODE TOGGLE */}
      <div className="flex gap-1 p-1 rounded-xl mb-5" style={{ background: "var(--scrim)" }}>
        {(["fitness", "explorer"] as AppMode[]).map((m) => (
          <button
            key={m}
            type="button"
            disabled={disabled}
            onClick={() => setAppMode(m)}
            className={`mode-tab disabled:opacity-40 disabled:cursor-not-allowed`}
            style={appMode === m ? { background: "var(--red)", color: "#fff" } : {}}
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
            onClick={() => { setTransport("walk"); setDistanceKm(Math.min(distanceKm, MAX_WALK_KM)) }} />
          <TransportBtn active={transport === "cycle"} icon={Bike} label="Cycle" disabled={disabled}
            onClick={() => { setTransport("cycle"); setDistanceKm(Math.min(distanceKm, MAX_CYCLE_KM)) }} />
        </div>
      </div>

      {/* ROUTE TYPE */}
      <div className="mb-5">
        <SectionLabel>Route Type</SectionLabel>
        <div className="flex gap-1 p-1 rounded-lg" style={{ background: "var(--scrim)" }}>
          {([["loop", "Loop", RotateCcw], ["a2b", "A → B", ArrowRight]] as const).map(([val, lbl, Icon]) => (
            <button
              key={val}
              type="button"
              disabled={disabled}
              onClick={() => setRouteType(val)}
              className={`route-type-btn disabled:opacity-40 disabled:cursor-not-allowed`}
              style={routeType === val ? { background: "var(--pill-hover)", color: "var(--fg)" } : {}}
            >
              <Icon size={12} className="inline mr-1.5" />
              {lbl}
            </button>
          ))}
        </div>
      </div>

      {/* START */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <SectionLabel>Start Point</SectionLabel>
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
        </div>
        <PlaceSearch
          mapboxToken={token}
          query={startLabel}
          onQueryChange={setStartLabel}
          disabled={disabled}
          onPlaceSelected={(lng, lat, label) => { setStartLng(lng); setStartLat(lat); setStartLabel(label) }}
          placeholder="Search address or place…"
        />
      </div>

      {/* END (A→B only) */}
      {routeType === "a2b" && (
        <div className="mb-4 animate-fade-up">
          <SectionLabel>End Point</SectionLabel>
          <PlaceSearch
            mapboxToken={token}
            query={endLabel}
            onQueryChange={setEndLabel}
            disabled={disabled}
            onPlaceSelected={(lng, lat, label) => { setEndLng(lng); setEndLat(lat); setEndLabel(label) }}
            placeholder="Search destination…"
          />
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
          <Slider min={5} max={maxKm} step={0.5} value={[distanceKm]} disabled={disabled}
            onValueChange={(v) => { const val = v[0]; if (val !== undefined) setDistanceKm(val) }} />
          <div className="flex justify-between mt-1 text-[10px]" style={{ color: "var(--fg-faint)" }}>
            <span>1 km</span><span>{maxKm} km</span>
          </div>
        </div>
      )}

      {/* DURATION (Explorer only) */}
      {routeType === "loop" && appMode === "explorer" && (
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
    </div>
  )
}
