// app/components/explorer/POICard.tsx
import { Plus } from "lucide-react"
import type { POI } from "@/types/poi"
import { formatPOICategory, getPOICategoryColor } from "@/lib/poiPresentation"

interface POICardProps {
  poi: POI
  index: number
  isSelected: boolean
  onSelect: (id: string) => void
  onAddWaypoint?: (lng: number, lat: number) => void // NEW
}

export function POICard({ poi, index, isSelected, onSelect, onAddWaypoint }: POICardProps): JSX.Element {
  const color = getPOICategoryColor(poi.category)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(poi.id)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelect(poi.id) }}
      className={`poi-card w-full text-left rounded-xl p-3.5 border transition-all cursor-pointer ${
        isSelected ? "selected" : ""
      }`}
      style={{
        background: isSelected ? "rgba(230,51,41,0.08)" : "rgba(255,255,255,0.03)",
        borderColor: isSelected ? "rgba(230,51,41,0.3)" : "rgba(255,255,255,0.07)",
        borderLeftWidth: "3px",
        borderLeftColor: isSelected ? "#e63329" : "transparent",
      }}
    >
      <div className="flex items-start gap-3">
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white mt-0.5"
          style={{ background: isSelected ? "#e63329" : "rgba(255,255,255,0.1)" }}
        >
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-white leading-tight truncate">
              {poi.name}
            </span>
            <span
              className="shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium"
              style={{ background: `${color}20`, color }}
            >
              {formatPOICategory(poi.category)}
            </span>
          </div>
          {poi.narration && (
            <p className="text-xs text-white/45 leading-relaxed line-clamp-2">
              {poi.narration}
            </p>
          )}
          <p className="text-[11px] text-white/25 mt-1.5">
            ~{poi.duration_suggested_minutes} min suggested
          </p>
        </div>
      </div>

      {/* NEW: Re-route Action Button */}
      {isSelected && onAddWaypoint && (
        <div className="mt-4 ml-10 border-t border-white/10 pt-3 animate-fade-up">
          <button
            type="button"
            onClick={(e) => { 
              e.stopPropagation() // Prevent card from collapsing
              onAddWaypoint(poi.lng, poi.lat) 
            }}
            className="flex items-center gap-1.5 text-[11px] font-semibold px-3 py-1.5 rounded-md transition-all hover:opacity-80"
            style={{ background: "var(--red)", color: "white" }}
          >
            <Plus size={12} /> Add to Route
          </button>
        </div>
      )}
    </div>
  )
}
