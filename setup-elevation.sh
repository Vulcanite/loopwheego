#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LoopWheeGo — OpenTopoData (SRTM30m) Docker Setup
#
# Usage:
#   ./setup-elevation.sh              # build + start (default port 2999)
#   ./setup-elevation.sh --port 3000  # custom port
#   ./setup-elevation.sh --stop       # stop container
#   ./setup-elevation.sh --status     # check status + test API
#
# Data: place .hgt tile files in backend/opentopodata/data/srtm30m/
#   Singapore tiles: N01E103.hgt, N01E104.hgt
#   Download from: https://www.opentopodata.org/datasets/srtm30m/
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

CONTAINER_NAME="loopwheego-opentopodata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENTOPODATA_DIR="${SCRIPT_DIR}/opentopodata"
HOST_PORT=2999
CONTAINER_PORT=5000

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC}  $*"; }
fail() { echo -e "${RED}  ✗${NC}  $*"; exit 1; }
info() { echo -e "${CYAN}  →${NC}  $*"; }
section() { echo -e "\n${CYAN}── $* ──${NC}"; }

# ── Parse args ───────────────────────────────────────────────────────────────
ACTION="start"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stop)   ACTION="stop"; shift ;;
        --status) ACTION="status"; shift ;;
        --port)   HOST_PORT="$2"; shift 2 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

# ── Stop ─────────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "stop" ]]; then
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker stop "${CONTAINER_NAME}" && docker rm "${CONTAINER_NAME}"
        ok "Stopped and removed ${CONTAINER_NAME}"
    else
        warn "${CONTAINER_NAME} not running"
    fi
    exit 0
fi

# ── Status ────────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "status" ]]; then
    section "Container status"
    if docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | grep "^${CONTAINER_NAME}"; then
        ok "Container running"
        section "API test (Singapore — Marina Bay)"
        curl -sf "http://localhost:${HOST_PORT}/v1/srtm30m?locations=1.2864,103.8534" | python3 -m json.tool || warn "API not responding"
    else
        warn "${CONTAINER_NAME} not running — run ./setup-elevation.sh to start"
    fi
    exit 0
fi

# ── Prereqs ───────────────────────────────────────────────────────────────────
section "Prerequisites"
command -v docker &>/dev/null || fail "Docker not found"
ok "Docker found"

# ── Validate tile data ────────────────────────────────────────────────────────
section "SRTM30m tile data"

TILE_DIR="${OPENTOPODATA_DIR}/data/srtm30m"

if [[ ! -d "${TILE_DIR}" ]]; then
    info "Creating tile directory: ${TILE_DIR}"
    mkdir -p "${TILE_DIR}"
fi

TILE_COUNT=$(find "${TILE_DIR}" -name "*.hgt" 2>/dev/null | wc -l)
if [[ "${TILE_COUNT}" -eq 0 ]]; then
    warn "No .hgt tile files found in ${TILE_DIR}"
    echo ""
    echo "  Download SRTM30m tiles covering your area:"
    echo "    Singapore: N01E103.hgt, N01E104.hgt"
    echo ""
    echo "  Option 1 — OpenTopoData SRTM30m (recommended):"
    echo "    https://www.opentopodata.org/datasets/srtm30m/"
    echo ""
    echo "  Option 2 — Direct download (NASA Earthdata, requires free account):"
    echo "    https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/"
    echo ""
    echo "  Option 3 — CGIAR-CSI (no account required, SRTM3 = 90m resolution):"
    echo "    https://srtm.csi.cgiar.org/srtmdata/"
    echo ""
    echo "  Place .hgt files in: ${TILE_DIR}"
    echo ""
    read -r -p "  Tiles not present. Continue anyway? [y/N] " yn
    [[ "${yn,,}" == "y" ]] || exit 1
else
    ok "${TILE_COUNT} tile(s) found:"
    find "${TILE_DIR}" -name "*.hgt" | sort | while read -r f; do
        echo "      $(basename "$f")  ($(du -sh "$f" | cut -f1))"
    done
fi

# ── Config ────────────────────────────────────────────────────────────────────
section "Config"

CONFIG_FILE="${OPENTOPODATA_DIR}/config.yaml"
if [[ ! -f "${CONFIG_FILE}" ]]; then
    info "Creating config.yaml"
    cat > "${CONFIG_FILE}" <<EOF
datasets:
  - name: srtm30m
    path: data/srtm30m/
EOF
    ok "Created config.yaml"
else
    ok "config.yaml exists"
fi

# ── Docker image ──────────────────────────────────────────────────────────────
section "Docker image"

IMAGE_NAME="loopwheego-opentopodata"
DOCKERFILE="${OPENTOPODATA_DIR}/docker/Dockerfile"

[[ -f "${DOCKERFILE}" ]] || fail "Dockerfile not found at ${DOCKERFILE}"

# Check if image needs rebuild
if docker image inspect "${IMAGE_NAME}" &>/dev/null; then
    ok "Image '${IMAGE_NAME}' already built"
    read -r -p "  Rebuild image? [y/N] " yn
    if [[ "${yn,,}" == "y" ]]; then
        info "Rebuilding image..."
        docker build -t "${IMAGE_NAME}" -f "${DOCKERFILE}" "${OPENTOPODATA_DIR}" \
            --progress=plain 2>&1 | tail -5
        ok "Image rebuilt"
    fi
else
    info "Building Docker image (first time — may take a few minutes)..."
    docker build -t "${IMAGE_NAME}" -f "${DOCKERFILE}" "${OPENTOPODATA_DIR}" \
        --progress=plain 2>&1 | tail -10
    ok "Image built"
fi

# ── Container ─────────────────────────────────────────────────────────────────
section "Container"

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    ok "${CONTAINER_NAME} already running on port ${HOST_PORT}"
else
    # Remove stopped container if exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        info "Removing stopped container"
        docker rm "${CONTAINER_NAME}" &>/dev/null
    fi

    info "Starting ${CONTAINER_NAME} on port ${HOST_PORT}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        -p "${HOST_PORT}:${CONTAINER_PORT}" \
        -v "${OPENTOPODATA_DIR}/data:/app/data:ro" \
        -v "${OPENTOPODATA_DIR}/config.yaml:/app/config.yaml:ro" \
        "${IMAGE_NAME}"

    ok "Container started"
fi

# ── Health check ──────────────────────────────────────────────────────────────
section "Health check"

info "Waiting for API to be ready..."
attempts=0
until curl -sf "http://localhost:${HOST_PORT}/health" &>/dev/null; do
    (( attempts++ ))
    if (( attempts >= 20 )); then
        warn "API not responding after 20s — check: docker logs ${CONTAINER_NAME}"
        break
    fi
    sleep 1
    printf "."
done
echo ""

if curl -sf "http://localhost:${HOST_PORT}/health" &>/dev/null; then
    ok "Health endpoint OK"

    section "Test queries"
    echo "  Marina Bay (flat):  $(curl -sf "http://localhost:${HOST_PORT}/v1/srtm30m?locations=1.2864,103.8534" | python3 -c "import sys,json; r=json.load(sys.stdin)['results'][0]; print(f'{r[\"elevation\"]}m')" 2>/dev/null || echo "parse error")"
    echo "  Bukit Timah (hill): $(curl -sf "http://localhost:${HOST_PORT}/v1/srtm30m?locations=1.3524,103.7759" | python3 -c "import sys,json; r=json.load(sys.stdin)['results'][0]; print(f'{r[\"elevation\"]}m')" 2>/dev/null || echo "parse error")"

    section "Backend .env"
    ENV_FILE="${SCRIPT_DIR}/.env"
    if [[ -f "${ENV_FILE}" ]]; then
        if grep -q "ELEVATION_API_URL" "${ENV_FILE}"; then
            # Update existing entry
            sed -i "s|^ELEVATION_API_URL=.*|ELEVATION_API_URL=http://localhost:${HOST_PORT}/v1/srtm30m|" "${ENV_FILE}"
            ok "Updated ELEVATION_API_URL in .env"
        else
            echo "ELEVATION_API_URL=http://localhost:${HOST_PORT}/v1/srtm30m" >> "${ENV_FILE}"
            ok "Added ELEVATION_API_URL to .env"
        fi
    else
        warn ".env not found — set manually: ELEVATION_API_URL=http://localhost:${HOST_PORT}/v1/srtm30m"
    fi
fi

echo ""
echo -e "${GREEN}  OpenTopoData ready:${NC} http://localhost:${HOST_PORT}/v1/srtm30m?locations=<lat>,<lng>"
echo ""
