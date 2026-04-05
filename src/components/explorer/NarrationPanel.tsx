// app/components/explorer/NarrationPanel.tsx
import { useEffect, useRef } from "react"
import { POICard } from "@/components/explorer/POICard"
import type { RouteResponse } from "@/types/route"

interface NarrationPanelProps {
  routeData: RouteResponse
  selectedPOI: string | null // REVERTED
  onSelectPOI: (id: string) => void
  onAddWaypoint?: (lng: number, lat: number) => void
}

export function NarrationPanel({ routeData, selectedPOI, onSelectPOI, onAddWaypoint }: NarrationPanelProps): JSX.Element {
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({})

  // Optional: Keep auto-scroll so when you click a map marker, it scrolls to the card
  useEffect(() => {
    if (!selectedPOI) return
    cardRefs.current[selectedPOI]?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }, [selectedPOI])

  return (
    <div className="flex flex-col gap-2 px-4 py-3 pb-6 border-t border-border">
      {routeData.pois.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--fg-faint)" }}>
          No points of interest found along this route.
        </p>
      ) : (
        routeData.pois.map((poi, i) => (
          <div key={poi.id} ref={(el) => { cardRefs.current[poi.id] = el }}>
            <POICard 
              poi={poi} 
              index={i} 
              isSelected={selectedPOI === poi.id} // REVERTED
              onSelect={onSelectPOI} 
              onAddWaypoint={onAddWaypoint} 
            />
          </div>
        ))
      )}
    </div>
  )
}