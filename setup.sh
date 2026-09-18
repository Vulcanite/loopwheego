#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# LoopWheeGo Backend Setup & Start Script
# Tested on: Ubuntu / RHEL / Rocky / AlmaLinux
# Usage:
#   ./setup.sh              # start everything
#   ./setup.sh --no-reload  # start without uvicorn --reload
#   ./setup.sh --no-docker  # skip local Docker services
#   ./setup.sh --with-elevation
#   ./setup.sh --with-overpass
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# ── Config (override via env vars or .env) ───────────────────
if [[ -z "${CONTAINER_DATA_DIR:-}" && -f "${SCRIPT_DIR}/.env" ]]; then
    ENV_CONTAINER_DATA_DIR="$(grep -E '^CONTAINER_DATA_DIR=' "${SCRIPT_DIR}/.env" | tail -n 1 | cut -d= -f2- || true)"
    [[ -n "${ENV_CONTAINER_DATA_DIR}" ]] && CONTAINER_DATA_DIR="${ENV_CONTAINER_DATA_DIR}"
fi
CONTAINER_DATA_DIR="${CONTAINER_DATA_DIR:-/home/ubuntu/container-data}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"

RELOAD=true
START_DOCKER=true
COMPOSE_PROFILE_NAMES=()

usage() {
    cat <<EOF
Usage: ./setup.sh [options]

Options:
  --no-reload        Start FastAPI without uvicorn reload
  --no-docker        Skip Docker compose services
  --with-elevation   Also start OpenTopoData via compose profile
  --with-overpass    Also start Overpass via compose profile
  -h, --help         Show this help

Environment:
  CONTAINER_DATA_DIR  Docker data root (default: /home/ubuntu/container-data)
  BACKEND_HOST        FastAPI bind host (default: 0.0.0.0)
  BACKEND_PORT        FastAPI port (default: 8000)
  COMPOSE_PROFILES    Comma-separated extra profiles, e.g. elevation,overpass
EOF
}

add_profile() {
    local profile=$1
    [[ -n "${profile}" ]] || return 0
    local existing
    for existing in "${COMPOSE_PROFILE_NAMES[@]}"; do
        [[ "${existing}" == "${profile}" ]] && return 0
    done
    COMPOSE_PROFILE_NAMES+=("${profile}")
}

if [[ -n "${COMPOSE_PROFILES:-}" ]]; then
    IFS=',' read -r -a _env_profiles <<< "${COMPOSE_PROFILES}"
    for _profile in "${_env_profiles[@]}"; do
        add_profile "${_profile}"
    done
fi

for arg in "$@"; do
    case "${arg}" in
        --no-reload)
            RELOAD=false
            ;;
        --no-docker)
            START_DOCKER=false
            ;;
        --with-elevation)
            add_profile "elevation"
            ;;
        --with-overpass)
            add_profile "overpass"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            echo "Unknown option: ${arg}" >&2
            exit 1
            ;;
    esac
done

# ── Colours ───────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC}  $*"; }
fail() { echo -e "${RED}  ✗${NC}  $*"; exit 1; }
info() { echo -e "${CYAN}  →${NC}  $*"; }
section() { echo -e "\n${CYAN}── $* ──${NC}"; }

# ─────────────────────────────────────────────────────────────
# 1. Prereq checks
# ─────────────────────────────────────────────────────────────
section "Checking prerequisites"

command -v python3 &>/dev/null || fail "python3 not found. Install: dnf install python3"
if [[ "${START_DOCKER}" == true ]]; then
    command -v docker &>/dev/null || fail "Docker not found. Install Docker first."
    docker compose version &>/dev/null || fail "Docker Compose v2 not found. Install the Docker compose plugin."
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python ${PYTHON_VER} found"

# ─────────────────────────────────────────────────────────────
# 2. .env
# ─────────────────────────────────────────────────────────────
section ".env"

if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
    warn ".env not found — creating with defaults"
    cat > "${SCRIPT_DIR}/.env" <<EOF
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
APP_ENV=development
API_PROXY_SECRET=
CONTAINER_DATA_DIR=${CONTAINER_DATA_DIR}
OSRM_FOOT_URL=http://localhost:5000
OSRM_BIKE_URL=http://localhost:5001
ALLOW_PUBLIC_OSRM_FALLBACK=false
NOMINATIM_BASE_URL=http://localhost:8080
ELEVATION_API_URL=http://localhost:2999/v1/srtm30m
ROUTE_TIMEOUT_S=45
ENABLE_POIS=true
OVERPASS_URL=http://localhost:12345/api/interpreter
EOF
    ok "Created .env — edit it to configure CORS, auth, routing, and POI discovery."
else
    ok ".env exists"
fi

# ─────────────────────────────────────────────────────────────
# 3. Docker services
# ─────────────────────────────────────────────────────────────
section "Docker services"

if [[ "${START_DOCKER}" == true ]]; then
    export CONTAINER_DATA_DIR
    mkdir -p "${CONTAINER_DATA_DIR}/osrm-data"

    COMPOSE_ARGS=()
    COMPOSE_SERVICES=(osrm-foot osrm-bike nominatim)

    for profile in "${COMPOSE_PROFILE_NAMES[@]}"; do
        case "${profile}" in
            elevation)
                COMPOSE_ARGS+=(--profile elevation)
                COMPOSE_SERVICES+=(opentopodata)
                ;;
            overpass)
                COMPOSE_ARGS+=(--profile overpass)
                COMPOSE_SERVICES+=(overpass)
                ;;
            *)
                warn "Ignoring unknown compose profile: ${profile}"
                ;;
        esac
    done

    info "Using container data dir: ${CONTAINER_DATA_DIR}"
    info "Starting compose services: ${COMPOSE_SERVICES[*]}"
    (
        cd "${SCRIPT_DIR}"
        docker compose "${COMPOSE_ARGS[@]}" up -d "${COMPOSE_SERVICES[@]}"
    )
    ok "Docker services requested"
else
    warn "Skipping Docker services (--no-docker)"
fi

# ─────────────────────────────────────────────────────────────
# 4. Python venv + dependencies
# ─────────────────────────────────────────────────────────────
section "Python environment"

if [[ ! -d "${VENV_DIR}" ]]; then
    info "Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    ok "Created venv at ${VENV_DIR}"
else
    ok "Venv exists at ${VENV_DIR}"
fi

info "Installing dependencies..."
"${VENV_DIR}/bin/pip" install -q --upgrade pip
"${VENV_DIR}/bin/pip" install -q -r "${SCRIPT_DIR}/requirements.txt"
ok "Dependencies installed"

# ─────────────────────────────────────────────────────────────
# 5. Start FastAPI
# ─────────────────────────────────────────────────────────────
section "Starting FastAPI"

UVICORN_ARGS=(
    app.main:app
    --host "${BACKEND_HOST}"
    --port "${BACKEND_PORT}"
)
[[ "${RELOAD}" == true ]] && UVICORN_ARGS+=(--reload)

info "Listening on http://${BACKEND_HOST}:${BACKEND_PORT}  (reload=${RELOAD})"
echo ""

cd "${SCRIPT_DIR}"
exec "${VENV_DIR}/bin/uvicorn" "${UVICORN_ARGS[@]}"
