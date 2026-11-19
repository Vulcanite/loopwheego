import os
import time

import httpx

PUBLIC_NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
LOCAL_NOMINATIM_BASE_URL = "http://localhost:8080"
PUBLIC_OSRM_BASE_URL = "https://router.project-osrm.org"
LOCAL_OSRM_FOOT_BASE_URL = "http://localhost:5000"
LOCAL_OSRM_BIKE_BASE_URL = "http://localhost:5001"
UNHEALTHY_TTL_S = float(os.getenv("EXTERNAL_ENDPOINT_UNHEALTHY_TTL_S", "60"))
_unhealthy_until: dict[str, float] = {}


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _is_public_base_url(base_url: str) -> bool:
    return base_url in {PUBLIC_NOMINATIM_BASE_URL, PUBLIC_OSRM_BASE_URL}


def _env_flag_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def is_base_url_temporarily_unhealthy(base_url: str) -> bool:
    if _is_public_base_url(base_url):
        return False
    until = _unhealthy_until.get(base_url, 0.0)
    return until > time.monotonic()


def mark_base_url_unhealthy(base_url: str) -> None:
    if _is_public_base_url(base_url):
        return
    _unhealthy_until[base_url] = time.monotonic() + UNHEALTHY_TTL_S


def should_fallback_on_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500

    return False


def get_nominatim_base_urls() -> list[str]:
    configured = os.getenv("NOMINATIM_BASE_URL", LOCAL_NOMINATIM_BASE_URL).rstrip("/")
    return [url for url in _unique([configured, PUBLIC_NOMINATIM_BASE_URL]) if not is_base_url_temporarily_unhealthy(url)]


def get_osrm_candidates(mode: str) -> list[tuple[str, str]]:
    normalized = mode.lower()
    if normalized == "cycle":
        configured_base = os.getenv("OSRM_BIKE_URL", LOCAL_OSRM_BIKE_BASE_URL).rstrip("/")
        configured_profile = "bicycle"
        public_profile = "cycling"
    else:
        configured_base = os.getenv("OSRM_FOOT_URL", LOCAL_OSRM_FOOT_BASE_URL).rstrip("/")
        configured_profile = "foot"
        public_profile = "walking"

    allow_public_osrm = _env_flag_enabled("ALLOW_PUBLIC_OSRM_FALLBACK")
    candidates = [(configured_base, configured_profile)]
    if allow_public_osrm:
        candidates.append((PUBLIC_OSRM_BASE_URL, public_profile))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate[0] == PUBLIC_OSRM_BASE_URL and not allow_public_osrm:
            continue
        if not is_base_url_temporarily_unhealthy(candidate[0]):
            out.append(candidate)
    return out
