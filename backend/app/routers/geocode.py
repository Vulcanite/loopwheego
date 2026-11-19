from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services.external_endpoints import (
    get_nominatim_base_urls,
    mark_base_url_unhealthy,
    should_fallback_on_error,
)

router = APIRouter()

SG_VIEWBOX = "103.60,1.48,104.05,1.13"


@router.get("/search")
async def search_places(
    q: str = Query(..., min_length=2, description="Free-text search query or postcode"),
) -> list[dict[str, Any]]:
    normalized = " ".join(q.replace("@", " ").replace(",", " ").replace(".", " ").split())
    if len(normalized) < 2:
        return []

    params: dict[str, str] = {
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "8",
        "countrycodes": "sg",
        "viewbox": SG_VIEWBOX,
        "bounded": "1",
    }

    if normalized.isdigit() and len(normalized) == 6:
        params["postalcode"] = normalized
        params["country"] = "Singapore"
    else:
        params["q"] = normalized

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=8.0) as client:
        for base_url in get_nominatim_base_urls():
            try:
                response = await client.get(
                    f"{base_url}/search",
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "LoopWheeGo/1.0",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, list) else []
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if should_fallback_on_error(exc):
                    mark_base_url_unhealthy(base_url)
                    continue
                break

    raise HTTPException(status_code=502, detail="Could not fetch search suggestions.") from last_error
