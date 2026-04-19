#!/usr/bin/env bash
# =============================================================================
# setup_opentopodata.sh
# Sets up opentopodata Docker container with the SRTM30m dataset.
#
# Usage:
#   chmod +x setup_opentopodata.sh
#   sudo ./setup_opentopodata.sh [OPTIONS]
#
# Options:
#   --data-dir DIR      Base directory for data (default: /opt/opentopodata)
#   --port PORT         Host port to expose the API (default: 5000)
#   --container NAME    Docker container name (default: opentopodata)
#   --tiles TILES       Space-separated list of SRTM tile names to download
#                       (default: a representative global set; use 'all' for all ~14k tiles)
#   --skip-download     Skip tile download (if tiles are already present)
#   --help              Show this help message
#
# Requirements:
#   - Docker
#   - wget or curl
#   - ~30 GB free disk space for a full global SRTM30m dataset
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
DATA_DIR="/opt/opentopodata"
HOST_PORT="5000"
CONTAINER_NAME="opentopodata"
SKIP_DOWNLOAD=false
TILE_LIST=()           # empty = use curated default set below

# SRTM30m tiles are hosted by AWS Open Data (no sign-in required)
SRTM_BASE_URL="https://s3.amazonaws.com/elevation-tiles-prod/skadi"

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
header()  { echo -e "\n${CYAN}══════════════════════════════════════════${RESET}"; \
            echo -e "${CYAN}  $*${RESET}"; \
            echo -e "${CYAN}══════════════════════════════════════════${RESET}"; }

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)      DATA_DIR="$2"; shift 2 ;;
    --port)          HOST_PORT="$2"; shift 2 ;;
    --container)     CONTAINER_NAME="$2"; shift 2 ;;
    --tiles)         shift; while [[ $# -gt 0 && "$1" != --* ]]; do TILE_LIST+=("$1"); shift; done ;;
    --skip-download) SKIP_DOWNLOAD=true; shift ;;
    --help)
      sed -n '/^# Usage:/,/^# =/p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) error "Unknown option: $1" ;;
  esac
done

SRTM_DIR="${DATA_DIR}/data/srtm30m"

# ── Default tile list (representative global coverage ~500 tiles, ~15 GB) ─────
# Full SRTM30m coverage uses the HGT filename convention: N/SDD + E/WXXX
# "all" triggers auto-generation of every valid SRTM tile.
DEFAULT_TILES_MODE="singapore"

generate_all_tiles() {
  local tiles=()
  for lat in $(seq -90 89); do
    local ns; [[ $lat -ge 0 ]] && ns="N" || ns="S"
    local abslat=$(( lat < 0 ? -lat : lat ))
    local lat_str; printf -v lat_str "%s%02d" "$ns" "$abslat"
    for lon in $(seq -180 179); do
      local ew; [[ $lon -ge 0 ]] && ew="E" || ew="W"
      local abslon=$(( lon < 0 ? -lon : lon ))
      local lon_str; printf -v lon_str "%s%03d" "$ew" "$abslon"
      tiles+=("${lat_str}${lon_str}")
    done
  done
  echo "${tiles[@]}"
}

# Singapore fits within a single SRTM tile: N01E103
# (covers 1°N–2°N, 103°E–104°E — the entire island is inside this tile)
SINGAPORE_TILES=(N01E103 N01E104)

# ── Dependency checks ──────────────────────────────────────────────────────────
check_deps() {
  header "Checking dependencies"
  local missing=()

  command -v docker  &>/dev/null || missing+=("docker")
  command -v git    &>/dev/null || missing+=("git")
  command -v wget    &>/dev/null || command -v curl &>/dev/null || missing+=("wget or curl")

  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing required tools: ${missing[*]}\nPlease install them and re-run."
  fi

  # Docker daemon running?
  docker info &>/dev/null || error "Docker daemon is not running. Start it first."

  success "All dependencies satisfied."
}

# ── Directory setup ────────────────────────────────────────────────────────────
setup_dirs() {
  header "Setting up directories"
  mkdir -p "${SRTM_DIR}"
  success "Data directory ready: ${SRTM_DIR}"
}

# ── Write opentopodata config ──────────────────────────────────────────────────
write_config() {
  header "Writing opentopodata configuration"
  local cfg="${DATA_DIR}/config.yaml"

  cat > "${cfg}" <<'EOF'
datasets:
- name: srtm30m
  path: data/srtm30m/
  filename_epsg: 4326
  filename_tile_size: 1
EOF

  success "Config written to ${cfg}"
}

# ── Tile downloader ────────────────────────────────────────────────────────────
download_tile() {
  local tile="$1"
  # Derive the directory component (N36, S23, …) from the tile name
  local ns_lat="${tile:0:3}"           # e.g. N36, S23
  local filename="${tile}.hgt.gz"
  local url="${SRTM_BASE_URL}/${ns_lat}/${filename}"
  local dest="${SRTM_DIR}/${filename%.gz}"   # store decompressed

  if [[ -f "${dest}" ]]; then
    info "  Already exists, skipping: ${tile}"
    return
  fi

  info "  Downloading: ${tile}"
  local tmpfile; tmpfile=$(mktemp)

  if command -v wget &>/dev/null; then
    wget -q --tries=3 --timeout=30 -O "${tmpfile}" "${url}" \
      || { warn "  Failed to download ${tile} (tile may not exist in SRTM dataset)"; rm -f "${tmpfile}"; return; }
  else
    curl -fsSL --retry 3 --max-time 30 -o "${tmpfile}" "${url}" \
      || { warn "  Failed to download ${tile} (tile may not exist in SRTM dataset)"; rm -f "${tmpfile}"; return; }
  fi

  gunzip -c "${tmpfile}" > "${dest}"
  rm -f "${tmpfile}"
  success "  Downloaded and extracted: ${tile}"
}

download_tiles() {
  header "Downloading SRTM30m tiles"

  local tiles_to_get=()

  if [[ ${#TILE_LIST[@]} -gt 0 ]]; then
    tiles_to_get=("${TILE_LIST[@]}")
    info "Using user-specified tile list (${#tiles_to_get[@]} tiles)"
  elif [[ "${DEFAULT_TILES_MODE}" == "all" ]]; then
    info "Generating full global tile list (~14400 tiles, ~30 GB)…"
    read -r -a tiles_to_get <<< "$(generate_all_tiles)"
  else
    tiles_to_get=("${SINGAPORE_TILES[@]}")
    info "Using Singapore tile set (${#tiles_to_get[@]} tile: ${SINGAPORE_TILES[*]})"
  fi

  local total=${#tiles_to_get[@]}
  local count=0

  for tile in "${tiles_to_get[@]}"; do
    (( count++ )) || true
    echo -ne "  Progress: ${count}/${total}\r"
    download_tile "${tile}"
  done

  echo ""
  success "Tile download complete. Files in ${SRTM_DIR}"
  info "Tile count: $(find "${SRTM_DIR}" -name '*.hgt' | wc -l)"
}

# ── Docker container setup ─────────────────────────────────────────────────────
setup_container() {
  header "Setting up Docker container"

  local repo_dir="${DATA_DIR}/opentopodata-src"
  local image_tag="opentopodata"

  # Clone or update the source repo
  if [[ -d "${repo_dir}/.git" ]]; then
    info "Source repo exists, pulling latest…"
    git -C "${repo_dir}" pull --ff-only
  else
    info "Cloning opentopodata source…"
    git clone --depth 1 https://github.com/ajnisbet/opentopodata.git "${repo_dir}"
  fi

  # Build the image
  info "Building Docker image '${image_tag}' (this may take a few minutes)…"
  docker build --tag "${image_tag}" --file "${repo_dir}/docker/Dockerfile" "${repo_dir}"

  # Remove existing container with same name
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "Container '${CONTAINER_NAME}' already exists — removing it."
    docker rm -f "${CONTAINER_NAME}" &>/dev/null
  fi

  info "Starting container '${CONTAINER_NAME}' on port ${HOST_PORT}…"
  docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -v "${DATA_DIR}/config.yaml:/app/config.yaml:ro" \
    -v "${DATA_DIR}/data:/app/data:ro" \
    -p "${HOST_PORT}:5000" \
    "${image_tag}"

  success "Container started."
}

# ── Smoke test ─────────────────────────────────────────────────────────────────
smoke_test() {
  header "Running smoke test"
  info "Waiting for API to become ready…"

  local retries=12 delay=5
  for ((i=1; i<=retries; i++)); do
    if curl -sf "http://localhost:${HOST_PORT}/health" &>/dev/null; then
      success "Health endpoint responded."
      break
    fi
    [[ $i -eq $retries ]] && error "API did not become ready after $((retries * delay))s. Check: docker logs ${CONTAINER_NAME}"
    sleep "${delay}"
  done

  # Query a sample point (Mount Everest)
  info "Querying elevation for Mount Everest (27.9881°N, 86.9250°E)…"
  local resp
  resp=$(curl -sf "http://localhost:${HOST_PORT}/v1/srtm30m?locations=27.9881,86.9250" 2>/dev/null || echo "FAILED")

  if echo "${resp}" | grep -q '"status":"OK"'; then
    local elev; elev=$(echo "${resp}" | grep -o '"elevation":[0-9.]*' | head -1 | cut -d: -f2)
    success "Elevation returned: ${elev} m  (expected ~8849 m for Everest)"
  else
    warn "Unexpected response: ${resp}"
    warn "This is normal if the Everest tile (N27E086) was not downloaded."
    info "To fetch it manually: $(dirname "$0")/setup_opentopodata.sh --skip-download --tiles N27E086"
  fi
}

# ── Print summary ──────────────────────────────────────────────────────────────
print_summary() {
  header "Setup complete"
  echo -e "  ${GREEN}Container:${RESET}  ${CONTAINER_NAME}"
  echo -e "  ${GREEN}API URL:${RESET}    http://localhost:${HOST_PORT}/v1/srtm30m"
  echo -e "  ${GREEN}Data dir:${RESET}   ${SRTM_DIR}"
  echo ""
  echo -e "  ${CYAN}Example queries:${RESET}"
  echo "    # Single point"
  echo "    curl 'http://localhost:${HOST_PORT}/v1/srtm30m?locations=27.9881,86.9250'"
  echo ""
  echo "    # Multiple points"
  echo "    curl 'http://localhost:${HOST_PORT}/v1/srtm30m?locations=27.9881,86.9250|1.3521,103.8198'"
  echo ""
  echo "    # Health check"
  echo "    curl 'http://localhost:${HOST_PORT}/health'"
  echo ""
  echo -e "  ${CYAN}Container management:${RESET}"
  echo "    docker logs   ${CONTAINER_NAME}   # view logs"
  echo "    docker stop   ${CONTAINER_NAME}   # stop"
  echo "    docker start  ${CONTAINER_NAME}   # restart"
  echo "    docker rm -f  ${CONTAINER_NAME}   # remove"
  echo ""
  echo -e "  ${CYAN}Add more tiles later:${RESET}"
  echo "    $0 --skip-download --tiles N01E103 S33E151"
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
  echo -e "${CYAN}"
  echo "  ╔═══════════════════════════════════════╗"
  echo "  ║   opentopodata + SRTM30m Setup        ║"
  echo "  ╚═══════════════════════════════════════╝"
  echo -e "${RESET}"

  check_deps
  setup_dirs
  write_config

  if [[ "${SKIP_DOWNLOAD}" == false ]]; then
    download_tiles
  else
    info "Skipping tile download (--skip-download)"
  fi

  setup_container
  smoke_test
  print_summary
}

main "$@"