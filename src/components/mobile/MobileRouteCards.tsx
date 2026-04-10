import { useRef } from "react"
import { ChevronLeft, ChevronRight, MapPin, Clock, Navigation, Bike, Footprints } from "lucide-react"
import type { RouteResponse } from "@/types/route"

interface MobileRouteCardsProps {
  routes: RouteResponse[]
  activeIdx: number
  onSelect: (idx: number) => void
  onOpenInGoogleMaps: () => void
}

const SWIPE_THRESHOLD = 40

export function MobileRouteCards({
  routes,
  activeIdx,
  onSelect,
  onOpenInGoogleMaps,
}: MobileRouteCardsProps): JSX.Element {
  const touchStartX = useRef<number | null>(null)

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]?.clientX ?? null
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return
    const dx = (e.changedTouches[0]?.clientX ?? 0) - touchStartX.current
    touchStartX.current = null
    if (Math.abs(dx) < SWIPE_THRESHOLD) return
    if (dx < 0 && activeIdx < routes.length - 1) onSelect(activeIdx + 1)
    if (dx > 0 && activeIdx > 0) onSelect(activeIdx - 1)
  }

  const active = routes[activeIdx]
  if (!active) return <></>
  const isCycle = active.source.includes("driving") || active.source.includes("bike") || active.source.includes("cycle")

  return (
    <div
      className="px-4 pt-1 pb-4 select-none"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold text-white"
            style={{ background: "var(--red)" }}
          >
            {String.fromCharCode(65 + activeIdx)}
          </span>
          <p className="text-sm font-semibold" style={{ color: "var(--fg)" }}>
            {active.label ?? `Route ${activeIdx + 1}`}
          </p>
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
          >
            {isCycle ? <Bike size={10} /> : <Footprints size={10} />}
            {isCycle ? "Cycle" : "Walk"}
          </span>
        </div>

        {/* Prev / dots / next */}
        {routes.length > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => activeIdx > 0 && onSelect(activeIdx - 1)}
              disabled={activeIdx === 0}
              className="p-1 rounded-lg disabled:opacity-30 transition-opacity"
              style={{ background: "var(--pill-bg)" }}
            >
              <ChevronLeft size={14} style={{ color: "var(--fg)" }} />
            </button>

            <div className="flex gap-1.5 items-center">
              {routes.map((_, i) => (
                <button
                  key={i}
                  onClick={() => onSelect(i)}
                  className="h-1.5 rounded-full transition-all duration-200"
                  style={{
                    width: i === activeIdx ? 20 : 6,
                    background: i === activeIdx ? "var(--red)" : "var(--border-mid)",
                  }}
                />
              ))}
            </div>

            <button
              onClick={() => activeIdx < routes.length - 1 && onSelect(activeIdx + 1)}
              disabled={activeIdx === routes.length - 1}
              className="p-1 rounded-lg disabled:opacity-30 transition-opacity"
              style={{ background: "var(--pill-bg)" }}
            >
              <ChevronRight size={14} style={{ color: "var(--fg)" }} />
            </button>
          </div>
        )}
      </div>

      {/* Stats card */}
      <div
        className="rounded-2xl px-5 py-4 flex items-center gap-5"
        style={{
          background: "var(--card)",
          border: "1.5px solid var(--red)",
          boxShadow: "0 0 0 4px color-mix(in srgb, var(--red) 12%, transparent)",
        }}
      >
        <div className="flex flex-col items-start">
          <span className="text-2xl font-bold tabular-nums leading-none" style={{ color: "var(--fg)" }}>
            {active.distance_km.toFixed(1)}
          </span>
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-widest mt-0.5" style={{ color: "var(--fg-faint)" }}>
            <MapPin size={9} /> km
          </span>
        </div>

        <div className="w-px h-9 shrink-0" style={{ background: "var(--border-mid)" }} />

        <div className="flex flex-col items-start">
          <span className="text-2xl font-bold tabular-nums leading-none" style={{ color: "var(--fg)" }}>
            {active.duration_minutes}
          </span>
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-widest mt-0.5" style={{ color: "var(--fg-faint)" }}>
            <Clock size={9} /> min
          </span>
        </div>

        <div className="ml-auto flex flex-col gap-2">
          {/* Open in Google Maps */}
          <button
            onClick={onOpenInGoogleMaps}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
          >
            <Navigation size={11} /> Google Maps
          </button>
        </div>
      </div>

      {routes.length > 1 && (
        <p className="text-center text-[11px] mt-2" style={{ color: "var(--fg)" }}>
          Swipe left / right to switch routes
        </p>
      )}
    </div>
  )
}
