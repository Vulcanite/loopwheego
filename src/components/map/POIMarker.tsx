import { useEffect } from "react"
import maplibregl from "maplibre-gl"
import type { POI } from "@/types/poi"
import { formatPOICategory, getPOICategoryColor } from "@/lib/poiPresentation"

interface POIMarkerProps {
  map: maplibregl.Map
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

    const popupContent = document.createElement("div")
    popupContent.style.maxWidth = "220px"

    const title = document.createElement("div")
    title.textContent = poi.name
    title.style.fontWeight = "700"
    title.style.fontSize = "13px"
    title.style.marginBottom = "4px"
    title.style.color = "#0f172a"

    const badge = document.createElement("div")
    badge.textContent = formatPOICategory(poi.category)
    badge.style.display = "inline-block"
    badge.style.fontSize = "10px"
    badge.style.fontWeight = "700"
    badge.style.padding = "2px 8px"
    badge.style.borderRadius = "999px"
    badge.style.marginBottom = "6px"
    badge.style.background = `${getPOICategoryColor(poi.category)}20`
    badge.style.color = getPOICategoryColor(poi.category)

    const body = document.createElement("div")
    body.textContent = poi.narration || `Suggested stop, around ${poi.duration_suggested_minutes} minutes.`
    body.style.fontSize = "12px"
    body.style.lineHeight = "1.45"
    body.style.color = "#334155"

    popupContent.appendChild(title)
    popupContent.appendChild(badge)
    popupContent.appendChild(body)

    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 18,
      maxWidth: "240px",
    }).setDOMContent(popupContent)

    const onClick = (e: MouseEvent): void => {
      e.stopPropagation()
      onSelect(poi.id)
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }
    el.addEventListener("click", onClick)
    const onMouseEnter = (): void => {
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }
    const onMouseLeave = (): void => {
      if (!isSelected) popup.remove()
    }
    el.addEventListener("mouseenter", onMouseEnter)
    el.addEventListener("mouseleave", onMouseLeave)

    el.style.background = isSelected ? "#c0271e" : getPOICategoryColor(poi.category)

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([poi.lng, poi.lat])
      .addTo(map)

    if (isSelected) {
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }

    return () => {
      el.removeEventListener("click", onClick)
      el.removeEventListener("mouseenter", onMouseEnter)
      el.removeEventListener("mouseleave", onMouseLeave)
      popup.remove()
      marker.remove()
    }
  }, [map, poi.category, poi.duration_suggested_minutes, poi.id, poi.lat, poi.lng, poi.name, poi.narration, index, onSelect, isSelected])

  return null
}
