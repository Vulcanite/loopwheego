import axios, { type AxiosError } from "axios"
import type { GPXRequest, RouteRequest, MultiRouteResponse, POIDiscoveryRequest } from "@/types/route"
import type { SuggestedPlace } from "@/types/place"
import { POI } from "@/types/poi"

const baseURL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")
const client = axios.create({ baseURL, headers: { "Content-Type": "application/json" } })

const ROUTE_TIMEOUT_MS = 60_000

function formatAxiosError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string | { msg: string }[] }>
    const d = ax.response?.data
    if (d && typeof d === "object" && "detail" in d) {
      const det = d.detail
      if (typeof det === "string") return det
      if (Array.isArray(det) && det[0]?.msg) return det.map((x) => x.msg).join(", ")
    }
    if (ax.code === "ECONNABORTED" || ax.message.toLowerCase().includes("timeout"))
      return "Route generation timed out. Please try again."
    return ax.message || "Request failed"
  }
  if (err instanceof Error) return err.message
  return "Something went wrong"
}

export { formatAxiosError }

export async function generateRouteVariants(request: RouteRequest): Promise<MultiRouteResponse> {
  const { data } = await client.post<MultiRouteResponse>("/routes/generate-variants", request, {
    timeout: ROUTE_TIMEOUT_MS,
  })
  return data
}

export async function getSuggestedPlaces(): Promise<SuggestedPlace[]> {
  const { data } = await client.get<SuggestedPlace[]>("/places/suggested")
  return data
}

export async function exportGPX(body: GPXRequest): Promise<Blob> {
  const { data } = await client.post<Blob>("/routes/export/gpx", body, { responseType: "blob" })
  return data
}

export async function discoverPOIs(request: POIDiscoveryRequest): Promise<POI[]> {
  const { data } = await client.post<POI[]>("/routes/discover-pois", request, {
    timeout: 60_000, 
  })
  return data
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<unknown[]> {
  const { data } = await client.get<unknown[]>("/geocode/search", {
    params: { q: query },
    timeout: 10_000,
    signal,
  })
  return data
}

export const api = { generateRouteVariants, getSuggestedPlaces, exportGPX, discoverPOIs, searchPlaces }
