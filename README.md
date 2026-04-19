# LoopWheeGo — Backend

FastAPI backend for LoopWheeGo, a walking and cycling route generation and discovery platform. Handles loop/A-to-B routing via OSRM, POI discovery via Overpass, LLM narration via Ollama or Groq, and GPX export.

## Tech Stack

- **Python 3.12** + FastAPI + Uvicorn
- **OSRM** — two Docker containers (foot + bicycle profiles)
- **Overpass API** — OSM-based POI discovery
- **Ollama / Groq** — LLM narration of POIs
- **gpxpy** — GPX file generation

## Prerequisites

- Python 3.12+
- Docker (for OSRM containers)
- [Ollama](https://ollama.com) with `llama3.1:8b` pulled, **or** a Groq API key

## OSRM Setup

Download and process OSM data before running the backend for the first time:

```bash
mkdir osrm-data && cd osrm-data

# Download region (example: Malaysia/Singapore/Brunei)
wget http://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf

# Foot profile
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-extract -p /opt/foot.lua /data/malaysia-singapore-brunei-latest.osm.pbf
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-partition /data/malaysia-singapore-brunei-latest.osrm
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-customize /data/malaysia-singapore-brunei-latest.osrm

# Bicycle profile (copy pbf, process separately)
cp malaysia-singapore-brunei-latest.osm.pbf bike.osm.pbf
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-extract -p /opt/bicycle.lua /data/bike.osm.pbf
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-partition /data/bike.osrm
docker run -t -v "${PWD}:/data" osrm/osrm-backend osrm-customize /data/bike.osrm
```

## Setup & Start

```bash
chmod +x setup.sh
./setup.sh             # starts OSRM containers, Ollama, venv, and FastAPI
./setup.sh --no-reload # production mode (no hot reload)
```

The script is idempotent — safe to re-run. It will skip steps already completed.

### Environment Variables

Copy and edit `.env` before running (auto-created with defaults by `setup.sh` if missing):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `groq` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b` | Model name |
| `GROQ_API_KEY` | — | Required if using Groq |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `OSRM_FOOT_URL` | `http://localhost:5000` | Foot OSRM container |
| `OSRM_BIKE_URL` | `http://localhost:5001` | Bicycle OSRM container |
| `ENABLE_POIS` | `true` | Enable Overpass POI discovery |
| `ENABLE_LLM_NARRATION` | `false` | Enable LLM narration of POIs |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins |
| `ROUTE_TIMEOUT_S` | `60` | OSRM request timeout |
| `OVERPASS_URL` | `https://overpass.kumi.systems/api/interpreter` | Overpass endpoint |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/routes/generate-variants` | Generate 3 route variants (loop or A-to-B) |
| `POST` | `/routes/discover-pois` | Discover POIs along a route |
| `POST` | `/routes/export/gpx` | Export route + POIs as GPX |
| `GET` | `/places/suggested` | List suggested places for the region |

## Refreshing Cached Explorer Places

The curated Explorer cache lives at `app/data/singapore_places_cached.json`.
Rebuild it from Overpass with:

```bash
python3 scripts/update_cached_places.py
```

The script normalizes raw OSM data into Explorer-facing categories and is
intended to be run periodically to refresh the cached place list.

## Running Tests

Requires the server and OSRM containers to be running:

```bash
python test_routes.py
```

Tests cover: health check, OSRM engines, Overpass, suggested places, LLM connectivity, and route generation.
