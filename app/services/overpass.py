import math
import os
from typing import Any

import httpx

OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

def _derive_category(tags: dict[str, str]) -> str:
    if tags.get("tourism"):
        return f"tourism:{tags['tourism']}"
    if tags.get("historic"):
        return f"historic:{tags['historic']}"
    if tags.get("leisure") == "park":
        return "leisure:park"
    if tags.get("amenity") == "cafe":
        return "amenity:cafe"
    if tags.get("natural") == "peak":
        return "natural:peak"
    return "poi"


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _select_spatially_distributed(
    candidates: list[dict[str, Any]], max_n: int
) -> list[dict[str, Any]]:
    if len(candidates) <= max_n:
        return candidates
    selected: list[dict[str, Any]] = [candidates[0]]
    remaining = candidates[1:]
    while len(selected) < max_n and remaining:
        best: dict[str, Any] | None = None
        best_score = -1.0
        for c in remaining:

            def min_dist_to_sel(pt: dict[str, Any]) -> float:
                return min(
                    _haversine_m(
                        pt["lat"], pt["lng"], s["lat"], s["lng"]
                    )
                    for s in selected
                )

            score = min_dist_to_sel(c)
            if score > best_score:
                best_score = score
                best = c
        if best is not None:
            selected.append(best)
            remaining = [x for x in remaining if x is not best]
    return selected


async def fetch_pois_along_route(
    polyline: list, max_pois: int = 8
) -> list[dict[str, Any]]:
    if not polyline or len(polyline) < 2:
        return []

    # 1. Calculate the midpoint of the route to use as a search center
    mid_idx = len(polyline) // 2
    mid_lng, mid_lat = float(polyline[mid_idx][0]), float(polyline[mid_idx][1])
    
    # 2. Build ONE query with a 1km radius to catch POIs for the whole loop area
    query = f"""[out:json][timeout:25];
    (
      node["tourism"](around:1000,{mid_lat},{mid_lng});
      node["historic"](around:1000,{mid_lat},{mid_lng});
      node["leisure"="park"](around:1000,{mid_lat},{mid_lng});
      node["amenity"="cafe"](around:1000,{mid_lat},{mid_lng});
    );
    out body;"""

    seen: dict[int, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                OVERPASS_URL,
                content=query,
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            response.raise_for_status()
            payload = response.json()
            
            for el in payload.get("elements", []):
                nid = el.get("id")
                tags = el.get("tags") or {}
                name = tags.get("name")
                if not name or nid in seen: continue
                
                seen[nid] = {
                    "osm_id": str(nid),
                    "name": str(name),
                    "lat": float(el["lat"]),
                    "lng": float(el["lon"]),
                    "category": _derive_category(tags),
                    "tags": {k: str(v) for k, v in tags.items()},
                }
        except Exception as ex:
            print(f"-> Overpass Fetch Error: {repr(ex)}")
            return []

    return _select_spatially_distributed(list(seen.values()), max_pois)
