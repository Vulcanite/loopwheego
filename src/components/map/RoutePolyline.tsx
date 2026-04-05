import { useEffect } from "react"
import type { GeoJSONSource, Map } from "mapbox-gl"

interface RoutePolylineProps {
  map: Map
  coordinates: [number, number][]
}

export function RoutePolyline({ map, coordinates }: RoutePolylineProps): null {
  useEffect(() => {
    const sourceId = "walking-route"
    const layerId = "walking-route-line"
    const glowId = "walking-route-glow"

    const remove = (): void => {
      if (map.getLayer(glowId)) map.removeLayer(glowId)
      if (map.getLayer(layerId)) map.removeLayer(layerId)
      if (map.getSource(sourceId)) map.removeSource(sourceId)
    }

    if (coordinates.length < 2) { remove(); return }

    const geojson: GeoJSON.Feature<GeoJSON.LineString> = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates },
    }

    const existing = map.getSource(sourceId) as GeoJSONSource | undefined
    if (existing) {
      existing.setData(geojson)
    } else {
      map.addSource(sourceId, { type: "geojson", data: geojson })
      // Glow layer
      map.addLayer({
        id: glowId,
        type: "line",
        source: sourceId,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#e63329",
          "line-width": 14,
          "line-opacity": 0.15,
          "line-blur": 4,
        },
      })
      // Main line
      map.addLayer({
        id: layerId,
        type: "line",
        source: sourceId,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#e63329",
          "line-width": 4,
          "line-opacity": 0.95,
        },
      })
    }

    return () => { remove() }
  }, [map, coordinates])

  return null
}