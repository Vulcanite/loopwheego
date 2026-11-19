import { useEffect } from "react"
import maplibregl from "maplibre-gl"

import type { POI } from "@/types/poi"
import { formatPOICategory, getPOICategoryColor } from "@/lib/poiPresentation"

interface ExplorerPreviewMarkerProps {
  map: maplibregl.Map
  poi: POI
}

export function ExplorerPreviewMarker({ map, poi }: ExplorerPreviewMarkerProps): null {
  useEffect(() => {
    const el = document.createElement("button")
    el.type = "button"
    el.style.cssText = `
      width: 12px; height: 12px;
      border-radius: 999px;
      border: 2px solid rgba(255,255,255,0.95);
      background: ${getPOICategoryColor(poi.category)};
      box-shadow: 0 2px 10px rgba(15,23,42,0.28);
      cursor: pointer;
    `

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
    body.textContent = poi.narration || ""
    body.style.fontSize = "12px"
    body.style.lineHeight = "1.45"
    body.style.color = "#334155"

    popupContent.appendChild(title)
    popupContent.appendChild(badge)
    popupContent.appendChild(body)

    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 14,
      maxWidth: "240px",
    }).setDOMContent(popupContent)

    const onMouseEnter = (): void => {
      popup.setLngLat([poi.lng, poi.lat]).addTo(map)
    }
    const onMouseLeave = (): void => {
      popup.remove()
    }
    el.addEventListener("mouseenter", onMouseEnter)
    el.addEventListener("mouseleave", onMouseLeave)

    const marker = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat([poi.lng, poi.lat])
      .addTo(map)

    return () => {
      el.removeEventListener("mouseenter", onMouseEnter)
      el.removeEventListener("mouseleave", onMouseLeave)
      popup.remove()
      marker.remove()
    }
  }, [map, poi.category, poi.lat, poi.lng, poi.name, poi.narration])

  return null
}
