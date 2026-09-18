# LoopWheeGo — Backend

FastAPI backend for LoopWheeGo, a walking and cycling route generation and discovery platform. Handles loop/A-to-B routing via OSRM, POI discovery via Overpass, and GPX export.

## Tech Stack

- **Python 3.12** + FastAPI + Uvicorn
- **OSRM** — two Docker containers (foot + bicycle profiles)
- **Overpass API** — OSM-based POI discovery
- **gpxpy** — GPX file generation

## Prerequisites

- Python 3.12+
- Docker (for OSRM containers)

## OSRM Setup

Download and process OSM data before running the backend for the first time:

```bash
mkdir osrm-data && cd osrm-data

# Download region (example: Malaysia/Singapore/Brunei)
wget http://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf

# Foot profile
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-extract -p /opt/foot.lua /data/malaysia-singapore-brunei-latest.osm.pbf
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-partition /data/malaysia-singapore-brunei-latest.osrm
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-customize /data/malaysia-singapore-brunei-latest.osrm

# Bicycle profile (copy pbf, process separately)
cp malaysia-singapore-brunei-latest.osm.pbf bike.osm.pbf
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-extract -p /opt/bicycle.lua /data/bike.osm.pbf
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-partition /data/bike.osrm
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend:v6.0.0 osrm-customize /data/bike.osrm
```

## Setup & Start

```bash
chmod +x setup.sh
./setup.sh             # starts OSRM + Nominatim via Docker Compose, venv, and FastAPI
./setup.sh --no-reload # production mode (no hot reload)
./setup.sh --no-docker # skip Docker services if they are already managed separately
./setup.sh --with-elevation # also start OpenTopoData
./setup.sh --with-overpass  # also start Overpass
```

The script is idempotent — safe to re-run. It will skip steps already completed.
By default it starts only the core local services. OpenTopoData and Overpass are compose profiles because their imports/builds are heavier.

### Environment Variables

Copy and edit `.env` before running (auto-created with defaults by `setup.sh` if missing):

| Variable             | Default                                  | Description                   |
|----------------------|------------------------------------------|-------------------------------|
| `OSRM_FOOT_URL`      | `http://localhost:5000`                  | Foot OSRM container              |
| `OSRM_BIKE_URL`      | `http://localhost:5001`                  | Bicycle OSRM container           |
| `ALLOW_PUBLIC_OSRM_FALLBACK` | `false`                          | Allow fallback to public OSRM     |
| `NOMINATIM_BASE_URL` | `http://localhost:8080`                  | Local Nominatim container        |
| `ELEVATION_API_URL`  | `http://localhost:2999/v1/srtm30m`       | Local OpenTopoData endpoint      |
| `ENABLE_POIS`        | `true`                                   | Enable legacy Overpass discovery |
| `CORS_ORIGINS`       | `http://localhost:3000`                  | Allowed frontend origins         |
| `CONTAINER_DATA_DIR` | `/home/ubuntu/container-data`            | Docker bind-mount root for OSRM/OpenTopoData data |
| `ROUTE_TIMEOUT_S`    | `45`                                     | OSRM request timeout (seconds)   |
| `OVERPASS_URL`       | `http://localhost:12345/api/interpreter` | Local Overpass endpoint          |
| `API_PROXY_SECRET`   | _(empty)_                                | Shared secret required by protected API routers |
| `APP_ENV`            | `development`                            | Set to `production` to require `API_PROXY_SECRET` at startup |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/routes/generate-variants` | Generate route variants (loop or A-to-B) |
| `POST` | `/routes/discover-pois` | Discover POIs along a route |
| `POST` | `/routes/export/gpx` | Export route + POIs as GPX |
| `GET` | `/places/suggested` | List suggested places for the region |

All endpoints except `/health` require `X-LoopWheeGo-Proxy-Token` when `API_PROXY_SECRET` is configured. In production, set `APP_ENV=production` and configure the same `API_PROXY_SECRET` in the Next.js frontend.

## Refreshing Cached Explorer Places

The curated Explorer cache lives at `app/data/singapore_places_cached.json`.
Explorer route generation reads that cache at runtime, and `/places/suggested`
serves it directly for fast map previews. Route-specific Explorer POIs and the
legacy `/routes/discover-pois` endpoint can still query the local Overpass
container within a bounded route area.

The maintainer script supports a safer fetch/build/validate pipeline:

```bash
python3 scripts/update_cached_places.py fetch
python3 scripts/update_cached_places.py build
python3 scripts/update_cached_places.py validate
python3 scripts/update_cached_places.py refresh
```

Notes:
- Raw per-category snapshots are stored under `app/data/raw_places/`.
- `refresh` fetches fresh snapshots, builds to a temporary file, validates it, and only then replaces the live cache.
- `validate` is lenient by default about legacy categories already present in an older cache. Use `--strict-categories` to fail on categories outside the current Explorer target set.

## Running Tests

The test script loads FastAPI in-process; no separate `uvicorn` server is required. It checks the expected local OSRM Foot, OSRM Cycle, Nominatim, Overpass, and OpenTopoData containers before route scenarios.

```bash
python test_routes.py
```

Tests cover: health check, OSRM engines, Overpass, suggested places, and route generation.

## Development Checks

Install the development tools when you want linting in addition to runtime dependencies:

```bash
python -m pip install -r requirements-dev.txt
ruff check app scripts test_routes.py
```
