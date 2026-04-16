import { Clock, MapPin } from "lucide-react"
import type { RouteResponse } from "@/types/route"

interface RouteVariantPickerProps {
  routes: RouteResponse[]
  activeIdx: number
  onSelect: (idx: number) => void
}

export function RouteVariantPicker({ routes, activeIdx, onSelect }: RouteVariantPickerProps): JSX.Element {
  return (
    <div
      className="px-4 pt-3 pb-4"
      style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}
    >
      <p className="text-[11px] uppercase tracking-widest mb-2.5 font-semibold" style={{ color: "var(--fg-faint)" }}>
        Choose a Route
      </p>
      <div className="flex flex-col gap-2">
        {routes.map((r, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(i)}
            className={`route-variant-card px-3.5 py-3 ${activeIdx === i ? "selected" : ""}`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span
                  className="flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold text-white shrink-0"
                  style={{ background: activeIdx === i ? "var(--red)" : "var(--border-mid)" }}
                >
                  {String.fromCharCode(65 + i)}
                </span>
                <div>
                  <p className="text-sm font-semibold leading-tight" style={{ color: "var(--fg)" }}>
                    {r.label ?? `Route ${i + 1}`}
                  </p>
                  {r.elevation_gain_m != null && (
                    <p className="text-[10px] mt-0.5" style={{ color: "var(--fg-faint)" }}>
                      ↑ {Math.round(r.elevation_gain_m)}m gain
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3 text-[11px]" style={{ color: "var(--fg-muted)" }}>
                <span className="flex items-center gap-1">
                  <MapPin size={10} />
                  {r.distance_km.toFixed(1)} km
                </span>
                <span className="flex items-center gap-1">
                  <Clock size={10} />
                  {r.duration_minutes} min
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
