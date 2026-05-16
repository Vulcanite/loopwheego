#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-loopwheego-backend}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
RUN_USER="${RUN_USER:-$(id -un)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
ENV_FILE="${SCRIPT_DIR}/.env"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok() { echo -e "${GREEN}  ✓${NC}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC}  $*"; }
info() { echo -e "${CYAN}  →${NC}  $*"; }
fail() { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        fail "Run with sudo/root because this writes ${SERVICE_FILE} and controls systemd."
    fi
}

detect_service_user() {
    if [[ "${RUN_USER}" == "root" && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        RUN_USER="${SUDO_USER}"
    fi
}

ensure_env() {
    if [[ -f "${ENV_FILE}" ]]; then
        ok ".env exists"
        return
    fi

    warn ".env not found; creating from .env.example/defaults"
    if [[ -f "${SCRIPT_DIR}/.env.example" ]]; then
        cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"
    else
        cat > "${ENV_FILE}" <<'EOF'
APP_ENV=production
API_PROXY_SECRET=replace_with_a_long_random_secret
CORS_ORIGINS=https://loopwheego.app,http://localhost:3000
CONTAINER_DATA_DIR=/home/ubuntu/container-data

OSRM_FOOT_URL=http://localhost:5000
OSRM_BIKE_URL=http://localhost:5001
ALLOW_PUBLIC_OSRM_FALLBACK=false
NOMINATIM_BASE_URL=http://localhost:8080
ELEVATION_API_URL=http://localhost:2999/v1/srtm30m
ENABLE_POIS=true
ROUTE_TIMEOUT_S=60
OVERPASS_URL=http://localhost:12345/api/interpreter
EOF
    fi
    warn "Edit ${ENV_FILE} before exposing production traffic, especially API_PROXY_SECRET and CORS_ORIGINS."
}

validate_env() {
    local app_env proxy_secret
    app_env="$(grep -E '^APP_ENV=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
    proxy_secret="$(grep -E '^API_PROXY_SECRET=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"

    if [[ "${app_env}" == "production" ]]; then
        if [[ -z "${proxy_secret}" || "${proxy_secret}" == "replace_with_a_long_random_secret" ]]; then
            fail "Set a real API_PROXY_SECRET in ${ENV_FILE}. Generate one with: openssl rand -base64 48"
        fi
    fi
}

install_python_deps() {
    command -v python3 >/dev/null 2>&1 || fail "python3 not found"

    if [[ ! -d "${VENV_DIR}" ]]; then
        info "Creating virtualenv at ${VENV_DIR}"
        python3 -m venv "${VENV_DIR}"
    else
        ok "Virtualenv exists"
    fi

    info "Installing Python dependencies"
    "${VENV_DIR}/bin/pip" install -q --upgrade pip
    "${VENV_DIR}/bin/pip" install -q -r "${SCRIPT_DIR}/requirements.txt"
    ok "Python dependencies installed"
}

write_service() {
    info "Writing ${SERVICE_FILE}"
    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=LoopWheeGo FastAPI Backend
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${SCRIPT_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python -m uvicorn app.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    ok "Systemd service written"
}

start_service() {
    info "Reloading systemd"
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}" >/dev/null
    systemctl restart "${SERVICE_NAME}"
    ok "Service started: ${SERVICE_NAME}"
}

print_status() {
    echo
    systemctl --no-pager --full status "${SERVICE_NAME}" || true
    echo
    echo "Health check:"
    echo "  curl http://${BACKEND_HOST}:${BACKEND_PORT}/health"
    echo
    echo "Logs:"
    echo "  journalctl -u ${SERVICE_NAME} -f"
}

require_root
detect_service_user

info "Repo: ${SCRIPT_DIR}"
info "Service: ${SERVICE_NAME}"
info "Run user: ${RUN_USER}"
info "Bind: ${BACKEND_HOST}:${BACKEND_PORT}"

ensure_env
validate_env
install_python_deps
write_service
start_service
print_status
