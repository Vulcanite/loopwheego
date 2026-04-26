from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.models.poi import POI

_DURATION_BY_CATEGORY: dict[str, int] = {
    "parks": 20,
    "waterfront": 15,
    "monuments": 15,
    "heritage": 20,
    "museums": 25,
    "viewpoints": 10,
    "hawker_centres": 30,
    "cafes": 20,
    "arts": 20,
    "nature": 20,
}

EXPLORER_SELECTABLE_CATEGORIES: tuple[str, ...] = (
    "parks",
    "nature",
    "waterfront",
    "monuments",
    "heritage",
    "museums",
    "viewpoints",
    "hawker_centres",
    "cafes",
    "arts",
)

_CATEGORY_WEIGHTS: dict[str, float] = {
    "monuments": 2.4,
    "heritage": 2.3,
    "waterfront": 2.2,
    "hawker_centres": 2.1,
    "museums": 1.9,
    "viewpoints": 1.8,
    "nature": 1.7,
    "parks": 1.2,
    "cafes": 0.8,
    "arts": 0.7,
}


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def load_cached_places() -> list[dict[str, Any]]:
    cached_path = _data_dir() / "singapore_places_cached.json"
    fallback_path = _data_dir() / "singapore_places.json"
    source_path = cached_path if cached_path.exists() else fallback_path

    with open(source_path, encoding="utf-8") as f:
        data = json.load(f)

    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                {
                    "id": str(item["id"]),
                    "name": str(item["name"]),
                    "lat": float(item["lat"]),
                    "lng": float(item["lng"]),
                    "category": str(item.get("category", "parks")),
                    "description": str(item.get("description", "")).strip(),
                    "_prominence": int(item.get("_prominence", 6)),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def available_categories() -> list[str]:
    return sorted({place["category"] for place in load_cached_places()})


def explorer_available_categories() -> list[str]:
    known = set(available_categories())
    return [category for category in EXPLORER_SELECTABLE_CATEGORIES if category in known]


def category_weight(category: str) -> float:
    return _CATEGORY_WEIGHTS.get(category, 1.0)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _point_to_segment_km(
    lat: float,
    lng: float,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> float:
    mean_lat = math.radians((start_lat + end_lat + lat) / 3.0)
    scale_x = 111.320 * math.cos(mean_lat)
    scale_y = 110.574

    px = lng * scale_x
    py = lat * scale_y
    ax = start_lng * scale_x
    ay = start_lat * scale_y
    bx = end_lng * scale_x
    by = end_lat * scale_y

    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab_len_sq = abx * abx + aby * aby

    if ab_len_sq <= 1e-9:
        dx = px - ax
        dy = py - ay
        return math.sqrt(dx * dx + dy * dy)

    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len_sq))
    proj_x = ax + t * abx
    proj_y = ay + t * aby
    dx = px - proj_x
    dy = py - proj_y
    return math.sqrt(dx * dx + dy * dy)


def _normalize_categories(categories: list[str] | None) -> list[str]:
    known = set(explorer_available_categories())
    requested = [cat for cat in (categories or []) if cat in known]
    return list(dict.fromkeys(requested))


def places_to_waypoints(places: list[dict[str, Any]]) -> list[tuple[float, float]]:
    return [(float(place["lng"]), float(place["lat"])) for place in places]


def places_to_pois(places: list[dict[str, Any]]) -> list[POI]:
    out: list[POI] = []
    for place in places:
        out.append(
            POI(
                id=str(place["id"]),
                name=str(place["name"]),
                lat=float(place["lat"]),
                lng=float(place["lng"]),
                category=str(place["category"]),
                narration=str(place.get("description", "")),
                duration_suggested_minutes=_DURATION_BY_CATEGORY.get(str(place["category"]), 15),
            )
        )
    return out


def pick_places_along_polyline(
    polyline: list[list[float]] | list[tuple[float, float]],
    categories: list[str] | None = None,
    exclude_ids: set[str] | None = None,
    limit: int = 6,
    corridor_km: float = 0.9,
) -> list[dict[str, Any]]:
    if not polyline or len(polyline) < 2:
        return []

    selected_categories = _normalize_categories(categories)
    excluded = exclude_ids or set()
    candidates = [place for place in load_cached_places() if place["category"] in selected_categories and place["id"] not in excluded]
    if not candidates:
        return []

    scored: list[dict[str, Any]] = []
    for place in candidates:
        min_dist_km = distance_to_polyline_km(place, polyline)
        if min_dist_km > corridor_km:
            continue

        score = float(place["_prominence"]) * 2.0 + category_weight(str(place["category"])) * 1.6 - min_dist_km * 6.0
        scored.append({**place, "_score": score, "_route_dist_km": min_dist_km})

    scored.sort(key=lambda item: (-float(item["_score"]), item["name"]))

    out: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for place in scored:
        if place["id"] in used_ids:
            continue
        out.append(place)
        used_ids.add(place["id"])
        if len(out) >= limit:
            break
    return out


def distance_to_polyline_km(
    place: dict[str, Any],
    polyline: list[list[float]] | list[tuple[float, float]],
) -> float:
    if not polyline or len(polyline) < 2:
        return float("inf")

    return min(
        _point_to_segment_km(
            float(place["lat"]),
            float(place["lng"]),
            float(polyline[idx][1]),
            float(polyline[idx][0]),
            float(polyline[idx + 1][1]),
            float(polyline[idx + 1][0]),
        )
        for idx in range(len(polyline) - 1)
    )


def _point_within_radius_km(
    lat: float,
    lng: float,
    center_lat: float,
    center_lng: float,
    radius_km: float,
) -> bool:
    return _haversine_km(lat, lng, center_lat, center_lng) <= radius_km


def _polyline_bounds(
    polyline: list[list[float]] | list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    lngs = [float(point[0]) for point in polyline]
    lats = [float(point[1]) for point in polyline]
    return min(lngs), min(lats), max(lngs), max(lats)


def _loop_zone_definitions(
    polyline: list[list[float]] | list[tuple[float, float]],
) -> list[dict[str, float | str]]:
    west, south, east, north = _polyline_bounds(polyline)
    width_km = _haversine_km((south + north) / 2.0, west, (south + north) / 2.0, east)
    height_km = _haversine_km(south, (west + east) / 2.0, north, (west + east) / 2.0)
    diag_km = _haversine_km(south, west, north, east)

    center_lat = (south + north) / 2.0
    center_lng = (west + east) / 2.0
    edge_radius_km = max(0.45, min(diag_km * 0.18, max(width_km, height_km) * 0.35, 1.8))
    center_radius_km = max(edge_radius_km * 0.95, min(diag_km * 0.42, 2.6))

    return [
        {"name": "center", "lat": center_lat, "lng": center_lng, "radius_km": center_radius_km, "weight": 0.9},
        {"name": "west", "lat": center_lat, "lng": west, "radius_km": edge_radius_km, "weight": 1.25},
        {"name": "north", "lat": north, "lng": center_lng, "radius_km": edge_radius_km, "weight": 1.25},
        {"name": "east", "lat": center_lat, "lng": east, "radius_km": edge_radius_km, "weight": 1.25},
        {"name": "south", "lat": south, "lng": center_lng, "radius_km": edge_radius_km, "weight": 1.1},
    ]


def pick_places_for_loop_area(
    polyline: list[list[float]] | list[tuple[float, float]],
    categories: list[str] | None = None,
    exclude_ids: set[str] | None = None,
    limit: int = 6,
    max_route_distance_km: float = 0.9,
    min_spacing_km: float = 0.35,
) -> list[dict[str, Any]]:
    if not polyline or len(polyline) < 2:
        return []

    selected_categories = _normalize_categories(categories)
    excluded = exclude_ids or set()
    if not selected_categories:
        return []

    zones = _loop_zone_definitions(polyline)
    candidates: list[dict[str, Any]] = []
    for place in load_cached_places():
        if place["category"] not in selected_categories or place["id"] in excluded:
            continue

        zone_hits = [
            zone for zone in zones
            if _point_within_radius_km(
                float(place["lat"]),
                float(place["lng"]),
                float(zone["lat"]),
                float(zone["lng"]),
                float(zone["radius_km"]),
            )
        ]
        if not zone_hits:
            continue

        route_dist_km = distance_to_polyline_km(place, polyline)
        if route_dist_km > max_route_distance_km:
            continue

        best_zone = max(zone_hits, key=lambda zone: float(zone["weight"]))
        zone_center_dist_km = _haversine_km(
            float(place["lat"]),
            float(place["lng"]),
            float(best_zone["lat"]),
            float(best_zone["lng"]),
        )
        score = (
            float(place["_prominence"]) * 2.0
            + category_weight(str(place["category"])) * 1.5
            + float(best_zone["weight"]) * 2.4
            + (len(zone_hits) - 1) * 0.55
            - route_dist_km * 3.2
            - zone_center_dist_km * 1.1
        )
        candidates.append(
            {
                **place,
                "_score": score,
                "_route_dist_km": route_dist_km,
                "_zone": str(best_zone["name"]),
                "_zone_hits": [str(zone["name"]) for zone in zone_hits],
                "_zone_center_dist_km": zone_center_dist_km,
            }
        )

    if not candidates:
        return []

    candidates.sort(
        key=lambda item: (
            -float(item["_score"]),
            float(item["_route_dist_km"]),
            item["name"],
        )
    )

    zone_counts: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for place in candidates:
        if any(
            _haversine_km(
                float(place["lat"]),
                float(place["lng"]),
                float(selected["lat"]),
                float(selected["lng"]),
            ) < min_spacing_km
            for selected in out
        ):
            continue

        zone = str(place["_zone"])
        diversity_penalty = zone_counts.get(zone, 0)
        adjusted = {**place, "_score": float(place["_score"]) - diversity_penalty * 1.1}
        if diversity_penalty > 0 and any(str(selected.get("_zone")) != zone for selected in out):
            adjusted["_score"] = float(adjusted["_score"]) - 0.35

        out.append(adjusted)
        zone_counts[zone] = zone_counts.get(zone, 0) + 1
        if len(out) >= limit:
            break

    return out
