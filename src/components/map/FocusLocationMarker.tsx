import { useEffect } from "react"
import maplibregl from "maplibre-gl"

interface FocusLocationMarkerProps {
  map: maplibregl.Map
  location: [number, number]
}

export function FocusLocationMarker({ map, location }: FocusLocationMarkerProps): null {
  useEffect(() => {
    const el = document.createElement("div")
    el.style.cssText = `
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: #e63329;
      border: 3px solid rgba(255,255,255,0.95);
      box-shadow: 0 0 0 6px rgba(230,51,41,0.18), 0 6px 18px rgba(15,23,42,0.22);
    `

    const marker = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat(location)
      .addTo(map)

    return () => {
      marker.remove()
    }
  }, [location, map])

  return null
}
