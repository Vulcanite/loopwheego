import { useEffect, useRef } from "react"
import { Clock, Download, MapPin, Plus } from "lucide-react"

import type { POI } from "@/types/poi"
import type { RouteResponse } from "@/types/route"
import { formatPOICategory, getPOICategoryColor } from "@/lib/poiPresentation"

interface DesktopExplorerOverlayProps {
  routeData: RouteResponse
  selectedPOI: string | null
  plannedStopsCount: number
  onSelectPOI: (id: string) => void
  onAddWaypoint?: (lng: number, lat: number, poiId: string) => void
  onExport: () => void
  addedPOIIds?: Set<string>
  canAddWaypoint?: boolean
}

export function DesktopExplorerOverlay({
  routeData,
  selectedPOI,
  plannedStopsCount,
  onSelectPOI,
  onAddWaypoint,
  onExport,
  addedPOIIds,
  canAddWaypoint = true,
}: DesktopExplorerOverlayProps): JSX.Element {
  const selectedIndex = Math.max(0, routeData.pois.findIndex((poi) => poi.id === selectedPOI))
  const activePOI = routeData.pois[selectedIndex] ?? routeData.pois[0] ?? null
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({})

  useEffect(() => {
    if (!activePOI) return
    cardRefs.current[activePOI.id]?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    })
  }, [activePOI])

  return (
    <section
      className="absolute bottom-3 left-4 right-4 z-20 grid overflow-hidden rounded-md border backdrop-blur-md"
      style={{
        background: "color-mix(in srgb, var(--surface) 94%, transparent)",
        borderColor: "var(--border-mid)",
        boxShadow: "0 18px 44px rgba(0,0,0,0.32)",
      }}
      aria-label="Route POI details"
    >
      <div className="flex items-center gap-4 border-b px-3 py-1.5" style={{ borderColor: "var(--border-mid)" }}>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-white" style={{ background: "var(--red)" }}>
            <MapPin size={13} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold" style={{ color: "var(--fg)" }}>Explorer POIs</p>
            <p className="truncate text-xs" style={{ color: "var(--fg-muted)" }}>
              {activePOI ? `${selectedIndex + 1} of ${routeData.pois.length}: ${activePOI.name}` : `${routeData.pois.length} POIs nearby`}
            </p>
          </div>
        </div>
        <Metric icon={<MapPin size={12} />} value={routeData.distance_km.toFixed(1)} label="km" />
        <Metric icon={<Clock size={12} />} value={String(routeData.duration_minutes)} label="min" />
        <Metric value={String(routeData.pois.length || plannedStopsCount)} label={routeData.pois.length ? "POIs" : "stops"} />
        <button
          type="button"
          onClick={onExport}
          className="flex h-8 w-8 items-center justify-center rounded-md transition-colors"
          style={{ background: "var(--pill-bg)", color: "var(--fg-muted)" }}
          aria-label="Export GPX"
        >
          <Download size={15} />
        </button>
      </div>

      <div
        className="poi-carousel-scroll flex gap-2 overflow-x-auto px-3 py-2"
        style={{
          scrollSnapType: "x mandatory",
        }}
      >
        {routeData.pois.map((poi, index) => (
          <POICarouselCard
            key={poi.id}
            refCallback={(el) => { cardRefs.current[poi.id] = el }}
            poi={poi}
            index={index}
            selected={activePOI?.id === poi.id}
            alreadyAdded={addedPOIIds?.has(poi.id) ?? false}
            canAddWaypoint={canAddWaypoint}
            onSelect={() => onSelectPOI(poi.id)}
            onAddWaypoint={onAddWaypoint}
          />
        ))}
      </div>
    </section>
  )
}

function Metric({ icon, value, label }: { icon?: JSX.Element; value: string; label: string }): JSX.Element {
  return (
    <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-muted)" }}>
      {icon ? <span style={{ color: "var(--red)" }}>{icon}</span> : null}
      <span className="font-semibold" style={{ color: "var(--fg)" }}>{value}</span>
      <span>{label}</span>
    </div>
  )
}

function POICarouselCard({
  refCallback,
  poi,
  index,
  selected,
  alreadyAdded,
  canAddWaypoint,
  onSelect,
  onAddWaypoint,
}: {
  refCallback: (el: HTMLDivElement | null) => void
  poi: POI
  index: number
  selected: boolean
  alreadyAdded: boolean
  canAddWaypoint: boolean
  onSelect: () => void
  onAddWaypoint?: (lng: number, lat: number, poiId: string) => void
}): JSX.Element {
  const color = getPOICategoryColor(poi.category)
  return (
    <div
      ref={refCallback}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return
        event.preventDefault()
        onSelect()
      }}
      className="grid h-[84px] w-[236px] shrink-0 grid-rows-[auto_1fr] gap-1.5 rounded-md p-2.5 text-left transition-colors"
      style={{
        scrollSnapAlign: "center",
        background: selected ? "color-mix(in srgb, var(--red) 13%, var(--app-card))" : "var(--app-card)",
        border: selected ? "1px solid color-mix(in srgb, var(--red) 42%, transparent)" : "1px solid var(--border-mid)",
      }}
    >
      <span className="grid grid-cols-[28px_minmax(0,1fr)] items-start gap-3">
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-bold"
          style={{ background: selected ? "var(--red)" : "var(--pill-bg)", color: selected ? "#fff" : "var(--fg)" }}
        >
          {index + 1}
        </span>
        <span className="min-w-0 pr-1">
          <span
            className="block overflow-hidden whitespace-nowrap text-ellipsis text-sm font-semibold leading-tight"
            style={{ color: "var(--fg)", maxWidth: "100%" }}
            title={poi.name}
          >
            {poi.name}
          </span>
          <span className="mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium" style={{ background: `${color}20`, color }}>
            {formatPOICategory(poi.category)}
          </span>
        </span>
      </span>

      <span className="flex items-end justify-between gap-2">
        <span className="min-w-0 truncate text-xs leading-relaxed" style={{ color: "var(--fg-muted)" }}>
          {poi.narration ?? ""}
        </span>
        {alreadyAdded ? (
          <span
            className="shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold"
            style={{ background: "color-mix(in srgb, var(--green) 12%, transparent)", color: "var(--green)" }}
          >
            Added
          </span>
        ) : onAddWaypoint ? (
          <button
            type="button"
            disabled={!canAddWaypoint}
            onClick={(event) => {
              event.stopPropagation()
              if (!canAddWaypoint) return
              onAddWaypoint(poi.lng, poi.lat, poi.id)
            }}
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "var(--red)", boxShadow: canAddWaypoint ? "0 8px 18px var(--red-glow)" : "none" }}
          >
            <Plus size={11} />
            {canAddWaypoint ? "Add" : "Full"}
          </button>
        ) : null}
      </span>
    </div>
  )
}
