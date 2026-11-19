# LoopWheeGo — Frontend

Next.js + TypeScript frontend for LoopWheeGo, a walking and cycling route generation and discovery platform. Renders routes on a MapLibre/MapTiler map, proxies API requests to FastAPI, supports POI discovery, variant picking, and GPX export.

## Tech Stack

- **Next.js 16** + **React 19** + TypeScript
- **MapLibre GL JS** — map rendering
- **shadcn/ui** + Tailwind CSS — UI components
- **Axios** — HTTP client

## Prerequisites

- Node.js 20.9+
- A [MapTiler](https://www.maptiler.com/) API key
- LoopWheeGo backend running (see backend README)

## Setup

```bash
npm install
```

Create a `.env` file in this directory:

```env
NEXT_PUBLIC_MAPTILER_KEY=your_maptiler_key_here
BACKEND_API_BASE_URL=http://localhost:8000
API_PROXY_SECRET=use_the_same_secret_as_fastapi
```

## Development

```bash
npm run dev
```

Runs on `http://localhost:3000` by default.

## Build

```bash
npm run build
npm run start
```

## Environment Variables

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_MAPTILER_KEY` | Browser-visible MapTiler key. Restrict it by domain in MapTiler. |
| `BACKEND_API_BASE_URL` | FastAPI base URL, used only by Next.js route handlers. |
| `API_PROXY_SECRET` | Shared secret sent from Next.js to FastAPI. Must match backend. |

## Features

- **Loop routing** — generate circular routes by target distance
- **A-to-B routing** — point-to-point with alternative variants
- **Route variants** — pick from up to 3 generated options
- **Explorer POIs** — preview cached regional places and rank route-specific POIs
- **Waypoint injection** — reroute through a selected POI, up to the backend waypoint limit
- **GPX export** — download route with POI waypoints for Strava, Garmin, etc.
- **Dark / light theme** — persisted via localStorage
