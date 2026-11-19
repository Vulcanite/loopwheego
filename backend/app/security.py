import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

PROXY_AUTH_HEADER = "X-LoopWheeGo-Proxy-Token"


def _api_proxy_secret() -> str:
    return os.getenv("API_PROXY_SECRET", "").strip()


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}


def validate_security_config() -> None:
    if _is_production() and not _api_proxy_secret():
        raise RuntimeError("API_PROXY_SECRET must be set when APP_ENV=production.")


async def require_proxy_auth(
    proxy_token: Annotated[str | None, Header(alias=PROXY_AUTH_HEADER)] = None,
) -> None:
    expected = _api_proxy_secret()
    if not expected:
        if _is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API proxy authentication is not configured.",
            )
        return

    if not proxy_token or not secrets.compare_digest(proxy_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized API request.",
        )
