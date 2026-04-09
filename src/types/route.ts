import type { POI } from "./poi"

export interface RouteRequest {
  start_lng: number
  start_lat: number
  distance_km?: number
  target_duration_minutes?: number
  appMode?: "explorer" | "fitness"
  mode: string
  routeType?: string;
  end_lng?: number | null;
  end_lat?: number | null;
  waypoints?: [number, number][];
}

export interface RouteResponse {
  polyline: [number, number][]
  distance_km: number
  duration_minutes: number
  pois: POI[]
  source: string;
}

export interface POIDiscoveryRequest {
  polyline: [number, number][]
  start_lng: number
  start_lat: number
  distance_km: number
}

export interface MultiRouteResponse {
  routes: RouteResponse[]
}

export interface GPXRequest {
  polyline: [number, number][]
  pois: POI[]
  route_name?: string
}
