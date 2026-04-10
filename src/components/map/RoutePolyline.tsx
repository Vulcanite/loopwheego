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
    const waypointSourceId = "route-waypoints"
    const waypointOuterId = "route-waypoints-outer"
    const waypointInnerId = "route-waypoints-inner"
    const waypointLabelId = "route-waypoints-label"

    const remove = (): void => {
      if (map.getLayer(waypointLabelId)) map.removeLayer(waypointLabelId)
      if (map.getLayer(waypointInnerId)) map.removeLayer(waypointInnerId)
      if (map.getLayer(waypointOuterId)) map.removeLayer(waypointOuterId)
      if (map.getSource(waypointSourceId)) map.removeSource(waypointSourceId)
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
    const startCoord = coordinates[0]
    const endCoord = coordinates[coordinates.length - 1]
    const sameStartEnd =
      Math.abs(startCoord[0] - endCoord[0]) < 0.00001 &&
      Math.abs(startCoord[1] - endCoord[1]) < 0.00001

    const waypointFeatures: GeoJSON.Feature<GeoJSON.Point>[] = [
      {
        type: "Feature",
        properties: { kind: "start", label: "Start Point" },
        geometry: { type: "Point", coordinates: startCoord },
      },
    ]
    if (!sameStartEnd) {
      waypointFeatures.push({
        type: "Feature",
        properties: { kind: "end", label: "End Point" },
        geometry: { type: "Point", coordinates: endCoord },
      })
    }
    const waypointsGeojson: GeoJSON.FeatureCollection<GeoJSON.Point> = {
      type: "FeatureCollection",
      features: waypointFeatures,
    }

    const existing = map.getSource(sourceId) as GeoJSONSource | undefined
    const existingWaypoints = map.getSource(waypointSourceId) as GeoJSONSource | undefined
    if (existing) {
      existing.setData(geojson)
      existingWaypoints?.setData(waypointsGeojson)
    } else {
      map.addSource(sourceId, { type: "geojson", data: geojson })
      map.addSource(waypointSourceId, { type: "geojson", data: waypointsGeojson })
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
      map.addLayer({
        id: waypointOuterId,
        type: "circle",
        source: waypointSourceId,
        paint: {
          "circle-color": "#ffffff",
          "circle-radius": 8,
          "circle-opacity": 0.95,
        },
      })
      map.addLayer({
        id: waypointInnerId,
        type: "circle",
        source: waypointSourceId,
        paint: {
          "circle-color": [
            "match",
            ["get", "kind"],
            "end",
            "#2563eb",
            "#e63329",
          ],
          "circle-radius": 4,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      })
      map.addLayer({
        id: waypointLabelId,
        type: "symbol",
        source: waypointSourceId,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 11,
          "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Regular"],
          "text-offset": [0, -1.7],
          "text-anchor": "top",
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#f8fafc",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.2,
        },
      })
    }

    return () => { remove() }
  }, [map, coordinates])

  return null
}
