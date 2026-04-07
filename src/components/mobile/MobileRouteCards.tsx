import { useRef } from "react"
import { ChevronLeft, ChevronRight, MapPin, Clock, Download } from "lucide-react"
import type { RouteResponse } from "@/types/route"

interface MobileRouteCardsProps {
  routes: RouteResponse[]
  activeIdx: number
  onSelect: (idx: number) => void
  onExport: () => void
  onOpenControls: () => void
}

const VARIANT_LABELS = ["Route A", "Route B", "Route C"]

const SWIPE_THRESHOLD = 40

export function MobileRouteCards({
  routes,
  activeIdx,
  onSelect,
  onExport,
  onOpenControls,
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
            {VARIANT_LABELS[activeIdx] ?? "Route"}
          </p>
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
          {/* Export GPX */}
          <button
            onClick={onExport}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
          >
            <Download size={11} /> GPX
          </button>
          {/* Re-plan */}
          <button
            onClick={onOpenControls}
            className="text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
          >
            Re-plan
          </button>
        </div>
      </div>

      {routes.length > 1 && (
        <p className="text-center text-[10px] mt-2" style={{ color: "var(--fg-faint)" }}>
          Swipe left / right to switch routes
        </p>
      )}
    </div>
  )
}
