import { useEffect } from "react"
import mapboxgl from "mapbox-gl"
import type { POI } from "@/types/poi"

interface POIMarkerProps {
  map: mapboxgl.Map
  poi: POI
  index: number
  isSelected: boolean
  onSelect: (id: string) => void
}

export function POIMarker({ map, poi, index, isSelected, onSelect }: POIMarkerProps): null {
  useEffect(() => {
    const el = document.createElement("button")
    el.type = "button"
    el.style.cssText = `
      width: 30px; height: 30px;
      border-radius: 50%;
      border: 2px solid white;
      background: ${isSelected ? "#c0271e" : "#e63329"};
      color: white;
      font-size: 11px;
      font-weight: 700;
      font-family: 'DM Sans', sans-serif;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      box-shadow: 0 2px 12px rgba(230,51,41,0.5);
      transform: ${isSelected ? "scale(1.2)" : "scale(1)"};
      transition: transform 0.2s ease;
    `
    el.textContent = String(index + 1)

    const onClick = (e: MouseEvent): void => {
      e.stopPropagation()
      onSelect(poi.id)
    }
    el.addEventListener("click", onClick)

    const getCatColor = (cat: string) => {
      const colors: Record<string, string> = {
        "tourism": "#f59e0b", "historic": "#f97316", "leisure:park": "#22c55e", "amenity:cafe": "#ec4899"
      }
      return colors[cat] || "#e63329"
    }
    
    el.style.background = isSelected ? "#c0271e" : getCatColor(poi.category);

    const marker = new mapboxgl.Marker({ element: el })
      .setLngLat([poi.lng, poi.lat])
      .addTo(map)

    return () => {
      el.removeEventListener("click", onClick)
      marker.remove()
    }
  }, [map, poi.id, poi.lat, poi.lng, index, onSelect, isSelected])

  return null
}