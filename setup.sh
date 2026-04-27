#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# LoopWheeGo Backend Setup & Start Script
# Tested on: RHEL / Rocky / AlmaLinux
# Usage:
#   ./setup.sh              # start everything
#   ./setup.sh --no-reload  # start without uvicorn --reload
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (override via env vars) ───────────────────────────
OSRM_DATA_DIR="${OSRM_DATA_DIR:-/root/osrm-data}"
FOOT_DATA="${FOOT_DATA:-malaysia-singapore-brunei-latest.osrm}"
BIKE_DATA="${BIKE_DATA:-bike-singapore.osrm}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
RELOAD=true
[[ "${1:-}" == "--no-reload" ]] && RELOAD=false

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

command -v docker  &>/dev/null || fail "Docker not found. Install: dnf install docker-ce"
command -v python3 &>/dev/null || fail "python3 not found. Install: dnf install python3"

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python ${PYTHON_VER} found"

if [[ ! -d "${OSRM_DATA_DIR}" ]]; then
    fail "OSRM data directory not found: ${OSRM_DATA_DIR}\nSet OSRM_DATA_DIR env var to the correct path."
fi
ok "OSRM data directory: ${OSRM_DATA_DIR}"

for f in "${FOOT_DATA}" "${BIKE_DATA}"; do
    [[ -f "${OSRM_DATA_DIR}/${f}" ]] || fail "OSRM data file missing: ${OSRM_DATA_DIR}/${f}"
done
ok "OSRM data files present"

# ─────────────────────────────────────────────────────────────
# 2. OSRM containers
# ─────────────────────────────────────────────────────────────
section "OSRM containers"

start_osrm_container() {
    local name=$1 host_port=$2 data_file=$3 profile=$4

    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        ok "${name} already running on port ${host_port}"
        return
    fi

    # Remove stopped container if it exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
        info "Removing stopped container: ${name}"
        docker rm "${name}" &>/dev/null
    fi

    info "Starting ${name} on port ${host_port}..."
    docker run -d \
        --name "${name}" \
        --restart unless-stopped \
        -p "${host_port}:5000" \
        -v "${OSRM_DATA_DIR}:/data" \
        osrm/osrm-backend \
        osrm-routed --algorithm mld "/data/${data_file}" \
        &>/dev/null

    # Wait for container to be healthy
    local attempts=0
    while (( attempts < 10 )); do
        if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
            ok "${name} started"
            return
        fi
        sleep 1
        (( attempts++ ))
    done
    warn "${name} may not have started — check: docker logs ${name}"
}

start_osrm_container "osrm-foot" 5000 "${FOOT_DATA}" "foot"
start_osrm_container "osrm-bike" 5001 "${BIKE_DATA}" "bicycle"

# ─────────────────────────────────────────────────────────────
# 3. Python venv + dependencies
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
# 4. .env
# ─────────────────────────────────────────────────────────────
section ".env"

if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
    warn ".env not found — creating with defaults"
    cat > "${SCRIPT_DIR}/.env" <<EOF
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
OSRM_FOOT_URL=http://localhost:5000
OSRM_BIKE_URL=http://localhost:5001
NOMINATIM_BASE_URL=http://localhost:8080
ELEVATION_API_URL=http://localhost:2999/v1/srtm30m
ROUTE_TIMEOUT_S=60
ENABLE_POIS=true
OVERPASS_URL=http://localhost:12345/api/interpreter
EOF
    ok "Created .env — edit it to configure CORS, routing, and POI discovery."
else
    ok ".env exists"
fi

# ─────────────────────────────────────────────────────────────
# 5. Start FastAPI
# ─────────────────────────────────────────────────────────────
section "Starting FastAPI"

UVICORN_ARGS=(
    app.main:app
    --host 0.0.0.0
    --port "${BACKEND_PORT}"
)
[[ "${RELOAD}" == true ]] && UVICORN_ARGS+=(--reload)

info "Listening on http://0.0.0.0:${BACKEND_PORT}  (reload=${RELOAD})"
echo ""

cd "${SCRIPT_DIR}"
exec "${VENV_DIR}/bin/uvicorn" "${UVICORN_ARGS[@]}"
