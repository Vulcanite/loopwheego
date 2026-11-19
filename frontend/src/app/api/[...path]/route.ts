import { type NextRequest } from "next/server"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"
export const maxDuration = 60

const PROXY_HEADER = "X-LoopWheeGo-Proxy-Token"
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition"] as const

const ALLOWED_PATHS: Record<string, Set<string>> = {
  GET: new Set(["places/suggested", "geocode/search"]),
  POST: new Set([
    "routes/generate-variants",
    "routes/discover-pois",
    "routes/export/gpx",
  ]),
}

type RouteContext = {
  params: Promise<{ path?: string[] }>
}

function apiError(detail: string, status: number): Response {
  return Response.json({ detail }, { status })
}

function getBackendConfig(): { baseUrl: string; token: string } | null {
  const baseUrl = process.env.BACKEND_API_BASE_URL?.replace(/\/$/, "")
  const token = process.env.API_PROXY_SECRET
  if (!baseUrl || !token) return null
  return { baseUrl, token }
}

async function proxyToBackend(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params
  const backendPath = path.join("/")
  const method = request.method.toUpperCase()

  if (!ALLOWED_PATHS[method]?.has(backendPath)) {
    return apiError("API route not found.", 404)
  }

  const config = getBackendConfig()
  if (!config) {
    return apiError("API proxy is not configured.", 500)
  }

  const incomingUrl = new URL(request.url)
  const backendUrl = new URL(`/${backendPath}`, config.baseUrl)
  backendUrl.search = incomingUrl.search

  const headers = new Headers({
    Accept: request.headers.get("accept") ?? "*/*",
    [PROXY_HEADER]: config.token,
  })

  const contentType = request.headers.get("content-type")
  if (contentType) headers.set("Content-Type", contentType)

  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  }

  if (method !== "GET" && method !== "HEAD") {
    init.body = await request.arrayBuffer()
  }

  const upstream = await fetch(backendUrl, init)
  const responseHeaders = new Headers()
  for (const header of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(header)
    if (value) responseHeaders.set(header, value)
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyToBackend(request, context)
}

export function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyToBackend(request, context)
}
