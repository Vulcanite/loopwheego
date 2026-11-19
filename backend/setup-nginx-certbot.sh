#!/usr/bin/env bash
set -euo pipefail

API_DOMAIN="${API_DOMAIN:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-loopwheego-api}"
NGINX_AVAILABLE="/etc/nginx/sites-available/${NGINX_SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${NGINX_SITE_NAME}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok() { echo -e "${GREEN}  ✓${NC}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC}  $*"; }
info() { echo -e "${CYAN}  →${NC}  $*"; }
fail() { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage:
  sudo API_DOMAIN=api.loopwheego.app CERTBOT_EMAIL=you@example.com ./setup-nginx-certbot.sh

Optional env:
  BACKEND_HOST=127.0.0.1
  BACKEND_PORT=8000
  NGINX_SITE_NAME=loopwheego-api

Notes:
  - DNS for API_DOMAIN must already point to this server.
  - Port 80 must be reachable from the internet for Let's Encrypt HTTP-01.
  - If Cloudflare proxy is enabled, SSL/TLS mode should be Full or Full (strict) after cert issuance.
EOF
}

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        fail "Run with sudo/root."
    fi
}

validate_inputs() {
    if [[ -z "${API_DOMAIN}" || -z "${CERTBOT_EMAIL}" ]]; then
        usage
        fail "Set API_DOMAIN and CERTBOT_EMAIL."
    fi
}

install_packages() {
    info "Installing nginx and certbot"
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx curl
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y nginx certbot python3-certbot-nginx curl
    else
        fail "Unsupported package manager. Install nginx, certbot, and python3-certbot-nginx manually."
    fi
    ok "Packages installed"
}

write_http_site() {
    info "Writing nginx HTTP proxy config: ${NGINX_AVAILABLE}"
    cat > "${NGINX_AVAILABLE}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${API_DOMAIN};

    client_max_body_size 10m;

    location / {
        proxy_pass http://${BACKEND_HOST}:${BACKEND_PORT};
        proxy_http_version 1.1;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 10s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
EOF

    ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
    ok "Nginx site enabled"
}

enable_nginx() {
    info "Validating nginx config"
    nginx -t
    systemctl enable nginx >/dev/null
    systemctl restart nginx
    ok "Nginx restarted"
}

check_backend() {
    info "Checking local FastAPI health"
    if ! curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/health" >/dev/null; then
        warn "FastAPI health check failed at http://${BACKEND_HOST}:${BACKEND_PORT}/health"
        warn "Certbot can still run, but API traffic will fail until systemd/FastAPI is running."
        return
    fi
    ok "FastAPI is reachable locally"
}

issue_certificate() {
    info "Requesting Let's Encrypt certificate for ${API_DOMAIN}"
    certbot --nginx \
        -d "${API_DOMAIN}" \
        --email "${CERTBOT_EMAIL}" \
        --agree-tos \
        --non-interactive \
        --redirect
    ok "Certificate installed"
}

enable_renewal_timer() {
    if systemctl list-unit-files | grep -q '^certbot.timer'; then
        systemctl enable --now certbot.timer >/dev/null
        ok "Certbot renewal timer enabled"
    else
        warn "certbot.timer not found; certbot package may use cron/systemd differently on this distro."
    fi
}

final_checks() {
    info "Final nginx validation"
    nginx -t
    systemctl reload nginx

    echo
    echo "Test commands:"
    echo "  curl -I https://${API_DOMAIN}/health"
    echo "  curl https://${API_DOMAIN}/health"
    echo
    echo "If Cloudflare is enabled:"
    echo "  DNS: ${API_DOMAIN} -> this server public IP"
    echo "  SSL/TLS mode: Full (strict) recommended"
}

require_root
validate_inputs

info "API domain: ${API_DOMAIN}"
info "Certbot email: ${CERTBOT_EMAIL}"
info "Proxy target: http://${BACKEND_HOST}:${BACKEND_PORT}"

install_packages
write_http_site
enable_nginx
check_backend
issue_certificate
enable_renewal_timer
final_checks
