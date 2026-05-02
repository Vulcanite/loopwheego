import math
import os
import uuid
from typing import Any

import httpx

from app.models.poi import POI

OVERPASS_URL = os.getenv("OVERPASS_URL", "http://localhost:12345/api/interpreter")

# Singapore bounding box
_SG_BBOX = (1.13, 103.60, 1.48, 104.05)

ALL_EXPLORER_CATEGORIES = [
    "parks", "nature", "waterfront", "monuments", "heritage",
    "museums", "viewpoints", "hawker_centres", "cafes", "arts",
]

# ─────────────────────────────────────────────
# Category → OSM tag filter mapping
# ─────────────────────────────────────────────

_CATEGORY_OSM_FILTERS: dict[str, list[str]] = {
    "parks":         ['["leisure"="park"]', '["leisure"="garden"]'],
    "nature":        ['["leisure"="nature_reserve"]', '["natural"~"wood|beach|grassland|wetland|scrub"]'],
    "waterfront":    ['["natural"="beach"]', '["amenity"="pier"]', '["waterway"="promenade"]'],
    "monuments":     ['["historic"~"monument|memorial|landmark"]', '["tourism"="attraction"]'],
    "heritage":      ['["historic"~"building|site|ruins|fort|castle|yes"]'],
    "museums":       ['["tourism"="museum"]'],
    "viewpoints":    ['["tourism"="viewpoint"]'],
    "hawker_centres":['["amenity"="food_court"]', '["amenity"="marketplace"]'],
    "cafes":         ['["amenity"="cafe"]'],
    "arts":          ['["tourism"="gallery"]', '["amenity"="arts_centre"]', '["tourism"="artwork"]'],
}

_DURATION_BY_CATEGORY: dict[str, int] = {
    "parks": 20, "waterfront": 15, "monuments": 15, "heritage": 20,
    "museums": 25, "viewpoints": 10, "hawker_centres": 30, "cafes": 20,
    "arts": 20, "nature": 20,
}


def _osm_tags_to_category(tags: dict[str, str], requested: set[str]) -> str | None:
    tourism  = tags.get("tourism", "")
    historic = tags.get("historic", "")
    amenity  = tags.get("amenity", "")
    leisure  = tags.get("leisure", "")
    natural  = tags.get("natural", "")
    waterway = tags.get("waterway", "")

    checks: list[tuple[str, bool]] = [
        ("museums",         tourism == "museum"),
        ("viewpoints",      tourism == "viewpoint"),
        ("arts",            tourism in ("gallery", "artwork")),
        ("arts",            amenity == "arts_centre"),
        ("monuments",       historic in ("monument", "memorial", "landmark")),
        ("monuments",       tourism == "attraction"),
        ("heritage",        historic in ("building", "site", "ruins", "fort", "castle", "yes")),
        ("cafes",           amenity == "cafe"),
        ("hawker_centres",  amenity in ("food_court", "marketplace")),
        ("waterfront",      natural == "beach" or amenity == "pier" or waterway == "promenade"),
        ("parks",           leisure in ("park", "garden")),
        ("nature",          leisure == "nature_reserve"),
        ("nature",          natural in ("wood", "grassland", "wetland", "scrub")),
    ]
    for category, match in checks:
        if match and category in requested:
            return category
    return None


def _osm_prominence(tags: dict[str, str]) -> float:
    score = 5.0
    if tags.get("wikipedia"):  score += 3.0
    if tags.get("wikidata"):   score += 2.0
    if tags.get("heritage"):   score += 1.5
    if tags.get("tourism") in ("attraction", "museum", "viewpoint"): score += 1.0
    return min(score, 10.0)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return _haversine_km(lat1, lng1, lat2, lng2) * 1000.0


def _point_to_segment_km(
    lat: float, lng: float,
    a_lat: float, a_lng: float,
    b_lat: float, b_lng: float,
) -> float:
    mean_lat = math.radians((a_lat + b_lat + lat) / 3.0)
    sx = 111.320 * math.cos(mean_lat)
    sy = 110.574
    px, py = lng * sx, lat * sy
    ax, ay = a_lng * sx, a_lat * sy
    bx, by = b_lng * sx, b_lat * sy
    abx, aby = bx - ax, by - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-9:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab2))
    return math.sqrt((px - ax - t * abx) ** 2 + (py - ay - t * aby) ** 2)


def _distance_to_polyline_km(
    lat: float, lng: float,
    polyline: list[list[float]] | list[tuple[float, float]],
) -> float:
    if len(polyline) < 2:
        return float("inf")
    return min(
        _point_to_segment_km(
            lat, lng,
            float(polyline[i][1]), float(polyline[i][0]),
            float(polyline[i + 1][1]), float(polyline[i + 1][0]),
        )
        for i in range(len(polyline) - 1)
    )


def _select_spatially_distributed(
    candidates: list[dict[str, Any]], max_n: int, min_spacing_km: float = 0.25
) -> list[dict[str, Any]]:
    if len(candidates) <= max_n:
        return candidates
    selected: list[dict[str, Any]] = [candidates[0]]
    remaining = candidates[1:]
    while len(selected) < max_n and remaining:
        best: dict[str, Any] | None = None
        best_score = -1.0
        for c in remaining:
            # Skip if too close to any already-selected
            min_d = min(_haversine_km(c["lat"], c["lng"], s["lat"], s["lng"]) for s in selected)
            if min_d < min_spacing_km:
                continue
            score = c.get("_score", 0.0)
            if score > best_score:
                best_score = score
                best = c
        if best is None:
            # Relax spacing: just pick highest score remaining
            remaining.sort(key=lambda x: -x.get("_score", 0.0))
            selected.append(remaining[0])
            remaining = remaining[1:]
        else:
            selected.append(best)
            remaining = [x for x in remaining if x is not best]
    return selected


def _polyline_bbox(
    polyline: list[list[float]] | list[tuple[float, float]],
    buffer_deg: float = 0.012,
) -> tuple[float, float, float, float]:
    lats = [float(p[1]) for p in polyline]
    lngs = [float(p[0]) for p in polyline]
    return (
        min(lats) - buffer_deg,
        min(lngs) - buffer_deg,
        max(lats) + buffer_deg,
        max(lngs) + buffer_deg,
    )


def _build_overpass_query(
    min_lat: float, min_lng: float, max_lat: float, max_lng: float,
    categories: list[str],
) -> str:
    bbox = f"{min_lat:.6f},{min_lng:.6f},{max_lat:.6f},{max_lng:.6f}"
    parts: list[str] = []
    seen_filters: set[str] = set()
    for cat in categories:
        for filt in _CATEGORY_OSM_FILTERS.get(cat, []):
            if filt in seen_filters:
                continue
            seen_filters.add(filt)
            parts.append(f'  node{filt}({bbox});')
            parts.append(f'  way{filt}({bbox});')
    if not parts:
        return ""
    body = "\n".join(parts)
    return f'[out:json][timeout:30];\n(\n{body}\n);\nout center;'


async def fetch_pois_for_explorer_routes(
    routes: list[dict],
    categories: list[str],
    max_per_route: int = 8,
    corridor_km: float = 0.5,
) -> list[list[POI]]:
    """
    Fetch POIs from Overpass once for all routes combined bbox.
    Returns per-route POI lists, each spatially distributed.
    """
    if not routes or not categories:
        return [[] for _ in routes]

    all_polylines = [route.get("polyline") or [] for route in routes]
    combined_poly = [pt for pl in all_polylines for pt in pl]
    if not combined_poly:
        return [[] for _ in routes]

    min_lat, min_lng, max_lat, max_lng = _polyline_bbox(combined_poly, buffer_deg=0.012)
    # Clamp to Singapore bounds — no query ever escapes SG
    sg_min_lat, sg_min_lng, sg_max_lat, sg_max_lng = _SG_BBOX
    min_lat = max(min_lat, sg_min_lat)
    min_lng = max(min_lng, sg_min_lng)
    max_lat = min(max_lat, sg_max_lat)
    max_lng = min(max_lng, sg_max_lng)
    query = _build_overpass_query(min_lat, min_lng, max_lat, max_lng, categories)
    if not query:
        return [[] for _ in routes]

    requested_set = set(categories)
    raw_pool: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=35.0) as client:
        try:
            resp = await client.post(
                OVERPASS_URL,
                content=query,
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as ex:
            print(f"-> Overpass explorer fetch error: {repr(ex)}")
            return [[] for _ in routes]

    seen_ids: set[int] = set()
    for el in payload.get("elements", []):
        eid = el.get("id")
        if eid in seen_ids:
            continue
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        # node: lat/lon direct; way: center.lat / center.lon
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        category = _osm_tags_to_category(tags, requested_set)
        if not category:
            continue
        seen_ids.add(eid)
        raw_pool.append({
            "osm_id": str(eid),
            "id": str(uuid.uuid4()),
            "name": str(name),
            "lat": float(lat),
            "lng": float(lng),
            "category": category,
            "tags": tags,
            "_prominence": _osm_prominence(tags),
        })

    print(f"-> Overpass explorer: {len(raw_pool)} named POIs in bbox for categories={categories}")

    # Per-route assignment: score each POI against each route's polyline
    result: list[list[POI]] = []
    for route in routes:
        polyline = route.get("polyline") or []
        if not polyline:
            result.append([])
            continue

        scored: list[dict[str, Any]] = []
        for poi in raw_pool:
            dist_km = _distance_to_polyline_km(poi["lat"], poi["lng"], polyline)
            if dist_km > corridor_km:
                continue
            score = poi["_prominence"] * 1.8 - dist_km * 5.0
            scored.append({**poi, "_score": score, "_dist_km": dist_km})

        scored.sort(key=lambda x: (-x["_score"], x["_dist_km"]))
        selected = _select_spatially_distributed(scored, max_per_route, min_spacing_km=0.25)

        pois: list[POI] = []
        for p in selected:
            pois.append(POI(
                id=p["id"],
                name=p["name"],
                lat=p["lat"],
                lng=p["lng"],
                category=p["category"],
                narration="",
                duration_suggested_minutes=_DURATION_BY_CATEGORY.get(p["category"], 15),
            ))
        result.append(pois)

    print(
        "-> Overpass explorer per-route POI counts: "
        + str([len(pois) for pois in result])
    )
    return result


async def fetch_suggested_places() -> list[dict[str, Any]]:
    """
    Fetch all named explorer POIs across Singapore for the map preview dots.
    Called once when the user enters explorer mode.
    """
    min_lat, min_lng, max_lat, max_lng = _SG_BBOX
    bbox = f"{min_lat},{min_lng},{max_lat},{max_lng}"

    # Way queries only for area-type categories — nodes cover most point features
    _WAY_CATS = {"parks", "nature", "heritage", "arts"}

    parts: list[str] = []
    seen_filters: set[str] = set()
    for cat in ALL_EXPLORER_CATEGORIES:
        for filt in _CATEGORY_OSM_FILTERS.get(cat, []):
            if filt in seen_filters:
                continue
            seen_filters.add(filt)
            name_filt = filt + '["name"]'
            parts.append(f'  node{name_filt}({bbox});')
            if cat in _WAY_CATS:
                parts.append(f'  way{name_filt}({bbox});')

    query = "[out:json][timeout:60][maxsize:134217728];\n(\n" + "\n".join(parts) + "\n);\nout center qt;"

    async with httpx.AsyncClient(timeout=65.0) as client:
        try:
            resp = await client.post(
                OVERPASS_URL,
                content=query,
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as ex:
            print(f"-> Overpass suggested places error: {repr(ex)}")
            return []

    requested_set = set(ALL_EXPLORER_CATEGORIES)
    seen_ids: set[int] = set()
    out: list[dict[str, Any]] = []

    for el in payload.get("elements", []):
        eid = el.get("id")
        if eid in seen_ids:
            continue
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        category = _osm_tags_to_category(tags, requested_set)
        if not category:
            continue
        seen_ids.add(eid)
        out.append({
            "id": str(eid),
            "name": str(name),
            "lat": float(lat),
            "lng": float(lng),
            "category": category,
            "description": tags.get("description", ""),
            "_prominence": _osm_prominence(tags),
        })

    print(f"-> Overpass suggested places: {len(out)} results")
    return out


# ─────────────────────────────────────────────
# Legacy: fetch POIs along a single route (fitness mode / discover-pois endpoint)
# ─────────────────────────────────────────────

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


async def fetch_pois_along_route(
    polyline: list, max_pois: int = 8
) -> list[dict[str, Any]]:
    if not polyline or len(polyline) < 2:
        return []

    mid_idx = len(polyline) // 2
    mid_lng, mid_lat = float(polyline[mid_idx][0]), float(polyline[mid_idx][1])

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
                if not name or nid in seen:
                    continue
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

    candidates = list(seen.values())
    if len(candidates) <= max_pois:
        return candidates

    selected: list[dict[str, Any]] = [candidates[0]]
    remaining = candidates[1:]
    while len(selected) < max_pois and remaining:
        best: dict[str, Any] | None = None
        best_score = -1.0
        for c in remaining:
            score = min(_haversine_m(c["lat"], c["lng"], s["lat"], s["lng"]) for s in selected)
            if score > best_score:
                best_score = score
                best = c
        if best is not None:
            selected.append(best)
            remaining = [x for x in remaining if x is not best]
    return selected
