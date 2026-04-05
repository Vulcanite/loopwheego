// app/pages/Home.tsx
import { useState } from "react"
import { Download, Clock, MapPin } from "lucide-react"

import { NarrationPanel } from "@/components/explorer/NarrationPanel"
import { MapView } from "@/components/map/MapView"
import { LoadingOverlay } from "@/components/shared/LoadingOverlay"
import { RouteControls } from "@/components/shared/RouteControls"
import { RouteVariantPicker } from "@/components/shared/RouteVariantPicker"
import type { RouteResponse } from "@/types/route"
import { api, formatAxiosError } from "@/services/api"
import type { POI } from "@/types/poi"
import { useToast } from "@/components/ui/use-toast"

export function Home(): JSX.Element {
  const { toast } = useToast()
  
  // Route State
  const [routes, setRoutes] = useState<RouteResponse[]>([])
  const [activeRouteIdx, setActiveRouteIdx] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  
  // POI & Interaction State
  const [selectedPOI, setSelectedPOI] = useState<string | null>(null)
  const [showPOIs, setShowPOIs] = useState(false)
  const [isDiscovering, setIsDiscovering] = useState(false)
  
  // Cache stores POIs by route index: { 0: [poi1, poi2], 1: [poi3] }
  const [poiCache, setPoiCache] = useState<Record<number, POI[]>>({})

  const activeRoute = routes[activeRouteIdx] ?? null

  // ─────────────────────────────────────────────────────────────
  // Handlers
  // ─────────────────────────────────────────────────────────────

  const handleRoutesGenerated = (newRoutes: RouteResponse[]) => {
    setRoutes(newRoutes)
    setActiveRouteIdx(0)
    setSelectedPOI(null)
    setPoiCache({})
    setShowPOIs(false)
  }

  const handleSelectVariant = (idx: number) => {
    setActiveRouteIdx(idx)
    setSelectedPOI(null)
    setShowPOIs(false)
  }

  const handleSelectPOI = (id: string) => {
    setSelectedPOI(prev => prev === id ? null : id)
  }

  const handleTogglePOIs = async () => {
    if (!activeRoute) return
    const nextState = !showPOIs
    setShowPOIs(nextState)

    // If toggling ON and we don't have this route cached, fetch it
    if (nextState && !poiCache[activeRouteIdx]) {
      setIsDiscovering(true)
      try {
        const pois = await api.discoverPOIs({
          polyline: activeRoute.polyline,
          start_lng: activeRoute.polyline[0][0],
          start_lat: activeRoute.polyline[0][1],
          distance_km: activeRoute.distance_km,
        })
        
        setPoiCache(prev => ({ ...prev, [activeRouteIdx]: pois }))
        
        setRoutes(prev => {
          const newRoutes = [...prev]
          newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois }
          return newRoutes
        })
      } catch (err) {
        console.error("Failed to fetch POIs", err)
        setShowPOIs(false)
        toast({ title: "Discovery Failed", description: "Could not fetch local places.", variant: "destructive" })
      } finally {
        setIsDiscovering(false)
      }
    } 
    // If it's cached, just re-inject it into the active route
    else if (nextState && poiCache[activeRouteIdx]) {
      setRoutes(prev => {
        const newRoutes = [...prev]
        newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois: poiCache[activeRouteIdx] }
        return newRoutes
      })
    } 
    // Toggled OFF: Strip POIs from active route to hide them, cache remains untouched
    else if (!nextState) {
      setRoutes(prev => {
        const newRoutes = [...prev]
        newRoutes[activeRouteIdx] = { ...newRoutes[activeRouteIdx], pois: [] }
        return newRoutes
      })
      setSelectedPOI(null)
    }
  }

  const handleAddWaypoint = async (lng: number, lat: number) => {
    if (!activeRoute) return
    setIsLoading(true)

    // Derive original route parameters from the source string and polyline
    const isLoop = activeRoute.source.includes('trip') || activeRoute.source.includes('loop')
    const isCycle = activeRoute.source.includes('driving') || activeRoute.source.includes('bike')
    const mode = isCycle ? 'cycle' : 'walk'
    const routeType = isLoop ? 'loop' : 'a2b'
    
    const startPt = activeRoute.polyline[0]
    const endPt = activeRoute.polyline[activeRoute.polyline.length - 1]

    try {
      const result = await api.generateRouteVariants({
        start_lng: startPt[0],
        start_lat: startPt[1],
        distance_km: activeRoute.distance_km,
        mode,
        routeType,
        end_lng: isLoop ? undefined : endPt[0],
        end_lat: isLoop ? undefined : endPt[1],
        waypoints: [[lng, lat]] // Pass the newly selected POI coordinates
      })

      setRoutes(result.routes)
      setActiveRouteIdx(0)
      setSelectedPOI(null)
      setPoiCache({}) // Clear cache since the path physically changed
      setShowPOIs(false)
      toast({ title: "Route updated", description: "Your route now passes through this location." })
    } catch (e) {
      toast({ title: "Rerouting failed", description: "Could not map a path through that location.", variant: "destructive" })
    } finally {
      setIsLoading(false)
    }
  }

  const handleExport = async (): Promise<void> => {
    if (!activeRoute) return
    try {
      const blob = await api.exportGPX({
        polyline: activeRoute.polyline,
        pois: activeRoute.pois,
        route_name: "LoopWheeGo Route",
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "loopwheego_route.gpx"
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      toast({ title: "GPX export failed", description: formatAxiosError(e), variant: "destructive" })
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────

  return (
    <div className="flex-1 flex overflow-hidden font-body">
      
      {/* SIDEBAR */}
      <aside
        className="w-[380px] shrink-0 flex flex-col overflow-y-auto"
        style={{ background: "var(--surface)", borderRight: "1px solid var(--sidebar-border)", zIndex: 10 }}
      >
        <RouteControls
          onRoutesGenerated={handleRoutesGenerated}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          hasRoutes={routes.length > 0}
        />

        {/* Route variant picker */}
        {routes.length > 1 && !isLoading && (
          <div className="animate-fade-up">
            <RouteVariantPicker
              routes={routes}
              activeIdx={activeRouteIdx}
              onSelect={handleSelectVariant}
            />
          </div>
        )}

        {/* STATS BAR (Always visible if a route exists) */}
        {activeRoute && !isLoading && (
          <div className="px-5 py-3 flex items-center gap-4 animate-fade-up" style={{ background: "var(--scrim)", borderTop: "1px solid var(--border)" }}>
            <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-muted)" }}>
              <MapPin size={12} style={{ color: "var(--red)" }} />
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{activeRoute.distance_km.toFixed(1)}</span> km
            </div>
            <div className="w-px h-3" style={{ background: "var(--border-mid)" }} />
            <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--fg-muted)" }}>
              <Clock size={12} style={{ color: "var(--red)" }} />
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{activeRoute.duration_minutes}</span> min
            </div>
            <div className="w-px h-3" style={{ background: "var(--border-mid)" }} />
            <div className="text-xs" style={{ color: "var(--fg-muted)" }}>
              <span className="font-semibold" style={{ color: "var(--fg)" }}>{poiCache[activeRouteIdx]?.length || 0}</span> stops
            </div>
            <button
              type="button"
              onClick={() => void handleExport()}
              className="ml-auto flex items-center gap-1.5 text-xs transition-colors py-1 px-2 rounded-md"
              style={{ color: "var(--fg-faint)" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--fg)"; (e.currentTarget as HTMLElement).style.background = "var(--pill-hover)" }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = "var(--fg-faint)"; (e.currentTarget as HTMLElement).style.background = "transparent" }}
            >
              <Download size={12} /> GPX
            </button>
          </div>
        )}

        {/* DISCOVER PLACES TOGGLE */}
        {routes.length > 0 && !isLoading && (
          <div className="px-5 py-4" style={{ borderTop: "1px solid var(--border)" }}>
            <label 
              htmlFor="poi-toggle"
              className="flex items-center justify-between cursor-pointer select-none group"
            >
              <div>
                <p className="text-[11px] uppercase tracking-widest font-semibold transition-colors group-hover:text-white" style={{ color: "var(--fg-faint)" }}>
                  Discover Places
                </p>
                <p className="text-[10px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
                  Find narrated landmarks along this path
                </p>
              </div>
              <div className="theme-switch">
                <input 
                  type="checkbox" 
                  id="poi-toggle" 
                  checked={showPOIs} 
                  onChange={handleTogglePOIs}
                  disabled={isDiscovering} 
                />
                {/* Notice how the track is self-closing now, and the thumb is below it! */}
                <div className="theme-switch-track" />
                <span className="theme-switch-thumb" />
              </div>
            </label>

            {/* Discovery Loading State */}
            {isDiscovering && (
              <div className="text-xs flex items-center gap-2 mt-4" style={{ color: "var(--red)" }}>
                <span className="animate-spin w-3 h-3 border-2 border-current border-t-transparent rounded-full" />
                Consulting local AI guide... (approx 10s)
              </div>
            )}

            {/* Empty State if POIs were loaded but 0 found */}
            {showPOIs && !isDiscovering && poiCache[activeRouteIdx]?.length === 0 && (
               <p className="text-xs mt-4 italic" style={{ color: "var(--fg-muted)" }}>No notable places found on this specific path.</p>
            )}
          </div>
        )}

        {/* POI NARRATION PANEL */}
        {activeRoute && activeRoute.pois.length > 0 && showPOIs && !isLoading && !isDiscovering && (
          <div className="animate-fade-up">
            <NarrationPanel
              routeData={activeRoute}
              selectedPOI={selectedPOI}
              onSelectPOI={handleSelectPOI}
              onAddWaypoint={handleAddWaypoint} 
            />
          </div>
        )}
      </aside>

      {/* MAP */}
      <main className="relative flex-1 overflow-hidden">
        <LoadingOverlay visible={isLoading} />
        <MapView
          routeData={activeRoute}
          selectedPOI={selectedPOI}
          onSelectPOI={handleSelectPOI}
        />
      </main>
      
    </div>
  )
}