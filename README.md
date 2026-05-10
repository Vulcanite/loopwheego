# LoopWheeGo — Frontend

React + TypeScript frontend for LoopWheeGo, a walking and cycling route generation and discovery platform. Renders routes on a MapLibre/MapTiler map, supports POI discovery, variant picking, and GPX export.

## Tech Stack

- **React 18** + TypeScript + Vite
- **MapLibre GL JS** — map rendering
- **shadcn/ui** + Tailwind CSS — UI components
- **Axios** — HTTP client

## Prerequisites

- Node.js 18+
- A [MapTiler](https://www.maptiler.com/) API key
- LoopWheeGo backend running (see backend README)

## Setup

```bash
npm install
```

Create a `.env` file in this directory:

```env
VITE_MAPTILER_KEY=your_maptiler_key_here
VITE_API_BASE_URL=http://localhost:8000
```

## Development

```bash
npm run dev
```

Runs on `http://localhost:5173` by default.

## Build

```bash
npm run build       # production build → dist/
npm run preview     # preview production build locally
```

## Environment Variables

| Variable            | Description                 |
|---------------------|-----------------------------|
| `VITE_MAPTILER_KEY` | MapTiler API key (required) |
| `VITE_API_BASE_URL` | Backend API base URL        |

## Features

- **Loop routing** — generate circular routes by target distance
- **A-to-B routing** — point-to-point with alternative variants
- **Route variants** — pick from up to 3 generated options
- **Explorer POIs** — preview cached regional places and rank route-specific POIs
- **Waypoint injection** — reroute through a selected POI, up to the backend waypoint limit
- **GPX export** — download route with POI waypoints for Strava, Garmin, etc.
- **Dark / light theme** — persisted via localStorage
