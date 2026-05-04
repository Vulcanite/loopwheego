import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useCallback, useEffect, useRef, useState } from "react"

import { ExplorerPreviewMarker } from "@/components/map/ExplorerPreviewMarker"
import { FocusLocationMarker } from "@/components/map/FocusLocationMarker"
import { POIMarker } from "@/components/map/POIMarker"
import { RoutePolyline } from "@/components/map/RoutePolyline"
import { useTheme } from "@/context/ThemeContext"
import type { POI } from "@/types/poi"
import type { RouteResponse } from "@/types/route"

interface MapViewProps {
  routeData: RouteResponse | null
  plannedStops: [number, number][]
  explorerPreviewPOIs?: POI[]
  focusLocation?: [number, number] | null
  onViewportChange?: (viewport: {
    west: number
    south: number
    east: number
    north: number
    zoom: number
  }) => void
  selectedPOI: string | null
  onSelectPOI: (id: string) => void
  onMapTap?: () => void
  fitPadding?: { top: number; right: number; bottom: number; left: number }
  fitTrigger?: number
  poiPopupMode?: "none" | "hover" | "sticky"
  minRoutePoiZoom?: number
  selectedPOIFocusOffset?: [number, number]
  addedPOIIds?: Set<string>
}

const SINGAPORE_BOUNDS: [[number, number], [number, number]] = [
  [103.6, 1.13], // Southwest coordinates
  [104.05, 1.48] // Northeast coordinates
];

const MAPTILER_KEY = (import.meta.env.VITE_MAPTILER_KEY ?? "").trim()

function getStyleUrl(theme: "dark" | "light"): string {
  const mapId = theme === "dark" ? "dataviz-dark" : "streets-v2"
  return `https://api.maptiler.com/maps/${mapId}/style.json?key=${MAPTILER_KEY}`
}

function flatten3DBuildingLayers(map: maplibregl.Map): void {
  const style = map.getStyle()
  const layers = style.layers ?? []
  for (const layer of layers) {
    if (layer.type !== "fill-extrusion") continue
    if (map.getLayer(layer.id)) {
      map.setPaintProperty(layer.id, "fill-extrusion-height", 0)
      map.setPaintProperty(layer.id, "fill-extrusion-base", 0)
      map.setPaintProperty(layer.id, "fill-extrusion-opacity", 0.85)
    }
  }
}

export function MapView({
  routeData,
  plannedStops,
  explorerPreviewPOIs = [],
  focusLocation = null,
  onViewportChange,
  selectedPOI,
  onSelectPOI,
  onMapTap,
  fitPadding,
  fitTrigger,
  poiPopupMode = "sticky",
  minRoutePoiZoom = 12,
  selectedPOIFocusOffset = [0, 0],
  addedPOIIds,
}: MapViewProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [map, setMap] = useState<maplibregl.Map | null>(null)
  const [styleEpoch, setStyleEpoch] = useState(0)
  const [initError, setInitError] = useState<string | null>(null)
  const [routePOIsVisible, setRoutePOIsVisible] = useState(true)
  const { theme } = useTheme()
  const [selectedPOIFocusOffsetX, selectedPOIFocusOffsetY] = selectedPOIFocusOffset

  const handleSelect = useCallback((id: string) => { onSelectPOI(id) }, [onSelectPOI])

  // Swap map style when theme changes
  useEffect(() => {
    if (!mapRef.current) return
    mapRef.current.setStyle(getStyleUrl(theme))
  }, [theme])

  useEffect(() => {
    if (!MAPTILER_KEY) {
      setInitError("MapTiler key missing. Set VITE_MAPTILER_KEY in your frontend env.")
      return
    }
    setInitError(null)
    if (!containerRef.current) return

    const m = new maplibregl.Map({
      container: containerRef.current,
      style: getStyleUrl(theme),
      center: [103.8198, 1.3521],
      maxBounds: SINGAPORE_BOUNDS,
      zoom: 11.5,
      minZoom: 10,
    })

    mapRef.current = m
    const onResize = (): void => { m.resize() }
    const onStyleLoad = (): void => {
      flatten3DBuildingLayers(m)
      setStyleEpoch((v) => v + 1)
    }

    m.on("load", () => {
      onResize()
      requestAnimationFrame(onResize)
      flatten3DBuildingLayers(m)
      setMap(m)
      const bounds = m.getBounds()
      onViewportChange?.({
        west: bounds.getWest(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        north: bounds.getNorth(),
        zoom: m.getZoom(),
      })
    })
    m.on("style.load", onStyleLoad)

    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right")

    const ro = typeof ResizeObserver !== "undefined" && containerRef.current
      ? new ResizeObserver(() => { onResize() }) : null
    ro?.observe(containerRef.current)

    return () => {
      m.off("style.load", onStyleLoad)
      ro?.disconnect()
      setMap(null)
      m.remove()
      mapRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const m = mapRef.current
    if (!m || !onViewportChange) return

    const emitViewport = (): void => {
      const bounds = m.getBounds()
      onViewportChange({
        west: bounds.getWest(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        north: bounds.getNorth(),
        zoom: m.getZoom(),
      })
    }

    m.on("moveend", emitViewport)
    m.on("zoomend", emitViewport)
    return () => {
      m.off("moveend", emitViewport)
      m.off("zoomend", emitViewport)
    }
  }, [onViewportChange])

  useEffect(() => {
    const m = mapRef.current
    if (!m) return

    const updateRoutePOIVisibility = (): void => {
      setRoutePOIsVisible(m.getZoom() >= minRoutePoiZoom)
    }

    updateRoutePOIVisibility()
    m.on("zoom", updateRoutePOIVisibility)
    m.on("zoomend", updateRoutePOIVisibility)

    return () => {
      m.off("zoom", updateRoutePOIVisibility)
      m.off("zoomend", updateRoutePOIVisibility)
    }
  }, [map, minRoutePoiZoom])

  useEffect(() => {
    const m = mapRef.current
    if (!m || !onMapTap) return
    m.on("click", onMapTap)
    return () => {
      m.off("click", onMapTap)
    }
  }, [onMapTap])

  const fitPaddingRef = useRef(fitPadding)
  fitPaddingRef.current = fitPadding

  const prevRouteRef = useRef<RouteResponse | null>(null)
  useEffect(() => {
    if (!map || !routeData?.polyline.length) return
    if (prevRouteRef.current === routeData) return
    prevRouteRef.current = routeData
    const coords = routeData.polyline
    const b = new maplibregl.LngLatBounds(coords[0], coords[0])
    coords.forEach(([lng, lat]) => { b.extend([lng, lat]) })
    map.fitBounds(b, { padding: fitPaddingRef.current ?? 80, duration: 900 })
  }, [map, routeData])

  // External fit-route trigger (zoom-out button)
  useEffect(() => {
    if (!map || !routeData?.polyline.length || fitTrigger === undefined) return
    const coords = routeData.polyline
    const b = new maplibregl.LngLatBounds(coords[0], coords[0])
    coords.forEach(([lng, lat]) => { b.extend([lng, lat]) })
    map.fitBounds(b, { padding: fitPaddingRef.current ?? 80, duration: 700 })
  }, [fitTrigger, map, routeData])

  useEffect(() => {
    if (!map || routeData || !focusLocation) return
    map.flyTo({
      center: focusLocation,
      zoom: Math.max(map.getZoom(), 13.5),
      duration: 700,
    })
  }, [focusLocation, map, routeData])

  useEffect(() => {
    if (!map || !routeData || !selectedPOI) return
    const poi = routeData.pois.find((item) => item.id === selectedPOI)
    if (!poi) return
    map.easeTo({
      center: [poi.lng, poi.lat],
      zoom: map.getZoom(),
      offset: [selectedPOIFocusOffsetX, selectedPOIFocusOffsetY],
      duration: 450,
      essential: true,
    })
  }, [map, routeData, selectedPOI, selectedPOIFocusOffsetX, selectedPOIFocusOffsetY])

  const coords = routeData?.polyline ?? []

  if (initError) {
    return (
      <div className="flex h-full w-full items-center justify-center text-center" style={{ background: "var(--bg)" }}>
        <div className="max-w-sm p-6 rounded-xl" style={{ background: "var(--card)", border: "1px solid var(--border-mid)" }}>
          <p className="font-semibold mb-2" style={{ color: "var(--red)" }}>Map Error</p>
          <p className="text-sm" style={{ color: "var(--fg-muted)" }}>{initError}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="absolute inset-0" />
      {map ? (
        <>
          <RoutePolyline key={`route-${styleEpoch}`} map={map} coordinates={coords} plannedStops={plannedStops} />
          {focusLocation ? <FocusLocationMarker key={`focus-${focusLocation[0]}-${focusLocation[1]}`} map={map} location={focusLocation} /> : null}
          {!routeData && explorerPreviewPOIs.map((poi) => (
            <ExplorerPreviewMarker key={`preview-${poi.id}`} map={map} poi={poi} />
          ))}
          {routePOIsVisible && routeData?.pois.map((poi, i) => (
            <POIMarker key={poi.id} map={map} poi={poi} index={i}
              isSelected={selectedPOI === poi.id} onSelect={handleSelect}
              popupMode={poiPopupMode}
              isAdded={addedPOIIds?.has(poi.id) ?? false}
            />
          ))}
        </>
      ) : null}
    </div>
  )
}
