import mapboxgl from "mapbox-gl"
import "mapbox-gl/dist/mapbox-gl.css"
import { useCallback, useEffect, useRef, useState } from "react"

import { POIMarker } from "@/components/map/POIMarker"
import { RoutePolyline } from "@/components/map/RoutePolyline"
import { useTheme } from "@/context/ThemeContext"
import type { RouteResponse } from "@/types/route"

interface MapViewProps {
  routeData: RouteResponse | null
  selectedPOI: string | null
  onSelectPOI: (id: string) => void
  onMapTap?: () => void
  fitPadding?: { top: number; right: number; bottom: number; left: number }
}

const SINGAPORE_BOUNDS: [[number, number], [number, number]] = [
  [103.6, 1.13], // Southwest coordinates
  [104.05, 1.48] // Northeast coordinates
];

export function MapView({
  routeData,
  selectedPOI,
  onSelectPOI,
  onMapTap,
  fitPadding,
}: MapViewProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const [map, setMap] = useState<mapboxgl.Map | null>(null)
  const [styleEpoch, setStyleEpoch] = useState(0)
  const [initError, setInitError] = useState<string | null>(null)
  const { theme } = useTheme()

  const handleSelect = useCallback((id: string) => { onSelectPOI(id) }, [onSelectPOI])

  // Swap map style when theme changes
  useEffect(() => {
    if (!mapRef.current) return
    const style = theme === "dark"
      ? "mapbox://styles/mapbox/dark-v11"
      : "mapbox://styles/mapbox/streets-v12"
    mapRef.current.setStyle(style)
  }, [theme])

  useEffect(() => {
    const raw = import.meta.env.VITE_MAPBOX_TOKEN
    const token = typeof raw === "string" ? raw.trim() : ""
    if (!token) {
      setInitError("Mapbox token missing — set VITE_MAPBOX_TOKEN in your .env file.")
      return
    }
    setInitError(null)
    mapboxgl.accessToken = token
    if (!containerRef.current) return

    const style = theme === "dark"
      ? "mapbox://styles/mapbox/dark-v11"
      : "mapbox://styles/mapbox/streets-v12"

    const m = new mapboxgl.Map({
      container: containerRef.current,
      style,
      center: [103.8198, 1.3521],
      maxBounds: SINGAPORE_BOUNDS,
      zoom: 11.5,
      minZoom: 10,
    })

    mapRef.current = m
    const onResize = (): void => { m.resize() }
    const onStyleLoad = (): void => { setStyleEpoch((v) => v + 1) }

    m.on("load", () => {
      onResize()
      requestAnimationFrame(onResize)
      setMap(m)
    })
    m.on("style.load", onStyleLoad)

    m.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "bottom-right")

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
    if (!m || !onMapTap) return
    m.on("click", onMapTap)
    return () => {
      m.off("click", onMapTap)
    }
  }, [onMapTap])

  useEffect(() => {
    if (!map || !routeData?.polyline.length) return
    const coords = routeData.polyline
    const b = new mapboxgl.LngLatBounds(coords[0], coords[0])
    coords.forEach(([lng, lat]) => { b.extend([lng, lat]) })
    map.fitBounds(b, { padding: fitPadding ?? 80, duration: 900 })
  }, [fitPadding, map, routeData])

  useEffect(() => {
    if (!map || !routeData || !selectedPOI) return
    const poi = routeData.pois.find((p) => p.id === selectedPOI)
    if (!poi) return
    map.flyTo({ center: [poi.lng, poi.lat], zoom: Math.max(map.getZoom(), 15), duration: 700 })
  }, [map, routeData, selectedPOI])

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
          <RoutePolyline key={`route-${styleEpoch}`} map={map} coordinates={coords} />
          {routeData?.pois.map((poi, i) => (
            <POIMarker key={poi.id} map={map} poi={poi} index={i}
              isSelected={selectedPOI === poi.id} onSelect={handleSelect} />
          ))}
        </>
      ) : null}
    </div>
  )
}
