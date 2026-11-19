import type { POI } from "./poi"

export type AppMode = "explorer" | "fitness"
export type TransportMode = "walk" | "cycle"
export type RouteType = "loop" | "a2b"

export interface RouteRequest {
  start_lng: number
  start_lat: number
  distance_km?: number
  target_duration_minutes?: number
  appMode?: AppMode
  mode: TransportMode
  routeType?: RouteType
  end_lng?: number | null
  end_lat?: number | null
  waypoints?: [number, number][]
  poi_categories?: string[]
  max_routes?: number
}

export interface RouteResponse {
  polyline: [number, number][]
  distance_km: number
  duration_minutes: number
  pois: POI[]
  source: string
  label?: string           // backend-computed = effort_label
  effort_label?: string    // "Easier" / "Balanced" / "Tougher"
  elevation_gain_m?: number // absent if elevation API was down
}

export interface POIDiscoveryRequest {
  polyline: [number, number][]
}

export interface MultiRouteResponse {
  routes: RouteResponse[]
}

export interface GPXRequest {
  polyline: [number, number][]
  pois: POI[]
  route_name?: string
}
