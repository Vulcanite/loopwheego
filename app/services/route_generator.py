"""
Closed-loop route generation service.

Strategy:
- Generate closed loops, not circular routes
- Build candidate anchors from:
    1) nearby seed places from singapore_places.json
    2) directional synthetic anchors around the start
- Build loop candidates as:
    start -> A -> B -> start
- Route each leg independently with OSRM /route
- Score by:
    - closeness to target distance
    - overlap penalty
    - angular spread of anchors
- Hard reject candidates that are too far from target

Primary engine: OSRM /route
Fallback      : small geometric triangle loop
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

import httpx

from app.services.external_endpoints import (
    get_osrm_candidates,
    mark_base_url_unhealthy,
    should_fallback_on_error,
)

ROUTE_TIMEOUT_S = float(os.getenv("ROUTE_TIMEOUT_S", "30"))

_MIN_LOOP_KM = 0.8
_MAX_ANCHORS = 16
_MAX_PAIR_CANDIDATES = 40
_MIN_ANGULAR_SEP_DEG = 35.0


# ─────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────

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


def _bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlng = math.radians(lng2 - lng1)

    y = math.sin(dlng) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlng)
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def _angular_sep_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _offset_point(lat: float, lng: float, north_m: float, east_m: float) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    cos_lat = max(math.cos(lat_rad), 1e-6)
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * cos_lat
    out_lat = lat + (north_m / m_per_deg_lat)
    out_lng = lng + (east_m / m_per_deg_lng)
    return out_lat, out_lng


def _merge_polylines(polylines: list[list[list[float]]]) -> list[list[float]]:
    out: list[list[float]] = []
    for poly in polylines:
        for pt in poly:
            lng = float(pt[0])
            lat = float(pt[1])
            if out and abs(out[-1][0] - lng) < 1e-9 and abs(out[-1][1] - lat) < 1e-9:
                continue
            out.append([lng, lat])
    return out


def _segment_key(
    a: list[float], b: list[float], places: int = 5
) -> tuple[tuple[float, float], tuple[float, float]]:
    p1 = (round(float(a[0]), places), round(float(a[1]), places))
    p2 = (round(float(b[0]), places), round(float(b[1]), places))
    return tuple(sorted((p1, p2)))


def _overlap_ratio(polyline: list[list[float]]) -> float:
    if len(polyline) < 3:
        return 1.0

    total_segments = 0
    seen: dict[tuple[tuple[float, float], tuple[float, float]], int] = {}

    for i in range(len(polyline) - 1):
        key = _segment_key(polyline[i], polyline[i + 1])
        seen[key] = seen.get(key, 0) + 1
        total_segments += 1

    if total_segments == 0:
        return 1.0

    repeated = sum(max(0, count - 1) for count in seen.values())
    return repeated / total_segments


# ─────────────────────────────────────────────────────────────
# Seed places / anchors
# ─────────────────────────────────────────────────────────────

def _load_seed_places() -> list[dict[str, Any]]:
    here = Path(__file__).resolve()
    data_path = here.parent.parent / "data" / "singapore_places.json"
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

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
                    "category": str(item.get("category", "place")),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _seed_place_anchors(
    start_lat: float,
    start_lng: float,
    distance_km: float,
) -> list[dict[str, Any]]:
    """
    For short loops, keep anchors tight.
    """
    d = max(distance_km, _MIN_LOOP_KM)

    if d <= 3.5:
        lower = 0.10 * d
        upper = 0.45 * d
    elif d <= 6.0:
        lower = 0.12 * d
        upper = 0.55 * d
    else:
        lower = 0.15 * d
        upper = 0.70 * d

    lower = max(0.18, lower)
    upper = max(lower + 0.20, upper)

    seeds = _load_seed_places()
    candidates: list[dict[str, Any]] = []

    for p in seeds:
        dist = _haversine_km(start_lat, start_lng, p["lat"], p["lng"])
        if dist < lower or dist > upper:
            continue

        bearing = _bearing_deg(start_lat, start_lng, p["lat"], p["lng"])
        candidates.append(
            {
                **p,
                "start_dist_km": dist,
                "bearing_deg": bearing,
                "kind": "seed_place",
            }
        )

    mid = (lower + upper) / 2.0
    candidates.sort(key=lambda x: abs(x["start_dist_km"] - mid))
    return candidates


def _directional_anchors(
    start_lat: float,
    start_lng: float,
    distance_km: float,
) -> list[dict[str, Any]]:
    """
    Synthetic candidate anchors in several directions.
    These are candidate anchors for loop construction, not forced circle points.
    """
    d = max(distance_km, _MIN_LOOP_KM)

    if d <= 3.5:
        rings_km = [
            max(0.22, 0.16 * d),
            max(0.38, 0.26 * d),
        ]
    elif d <= 6.0:
        rings_km = [
            max(0.35, 0.18 * d),
            max(0.55, 0.32 * d),
        ]
    else:
        rings_km = [
            max(0.55, 0.20 * d),
            max(0.90, 0.36 * d),
        ]

    angles_deg = [0, 45, 90, 135, 180, 225, 270, 315]
    anchors: list[dict[str, Any]] = []

    for ring_idx, radius_km in enumerate(rings_km, start=1):
        radius_m = radius_km * 1000.0
        for angle in angles_deg:
            theta = math.radians(angle)
            north_m = radius_m * math.cos(theta)
            east_m = radius_m * math.sin(theta)
            lat, lng = _offset_point(start_lat, start_lng, north_m, east_m)

            anchors.append(
                {
                    "id": f"dir-r{ring_idx}-{angle}",
                    "name": f"dir-r{ring_idx}-{angle}",
                    "lat": lat,
                    "lng": lng,
                    "category": "directional",
                    "start_dist_km": radius_km,
                    "bearing_deg": float(angle),
                    "kind": "directional",
                }
            )

    return anchors


def _dedupe_anchor_bearing_buckets(
    anchors: list[dict[str, Any]],
    max_anchors: int = _MAX_ANCHORS,
) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    used_buckets: set[int] = set()

    def sort_key(a: dict[str, Any]) -> tuple[int, float]:
        kind_rank = 0 if a.get("kind") == "seed_place" else 1
        return (kind_rank, float(a["start_dist_km"]))

    for a in sorted(anchors, key=sort_key):
        bucket = int(float(a["bearing_deg"]) // 22.5)
        if bucket in used_buckets and len(picked) < max_anchors // 2:
            continue
        used_buckets.add(bucket)
        picked.append(a)
        if len(picked) >= max_anchors:
            return picked

    return picked[:max_anchors]


def _generate_candidate_anchors(
    start_lat: float,
    start_lng: float,
    distance_km: float,
) -> list[dict[str, Any]]:
    seed = _seed_place_anchors(start_lat, start_lng, distance_km)
    directional = _directional_anchors(start_lat, start_lng, distance_km)
    merged = seed + directional
    return _dedupe_anchor_bearing_buckets(merged, _MAX_ANCHORS)


def _triangle_estimate_km(
    start_lat: float,
    start_lng: float,
    a: dict[str, Any],
    b: dict[str, Any],
) -> float:
    sa = _haversine_km(start_lat, start_lng, float(a["lat"]), float(a["lng"]))
    ab = _haversine_km(float(a["lat"]), float(a["lng"]), float(b["lat"]), float(b["lng"]))
    bs = _haversine_km(float(b["lat"]), float(b["lng"]), start_lat, start_lng)
    return sa + ab + bs


def _candidate_anchor_pairs(
    start_lat: float,
    start_lng: float,
    anchors: list[dict[str, Any]],
    target_distance_km: float,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any], float]] = []

    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            a = anchors[i]
            b = anchors[j]

            sep = _angular_sep_deg(float(a["bearing_deg"]), float(b["bearing_deg"]))
            if sep < _MIN_ANGULAR_SEP_DEG:
                continue

            ab_km = _haversine_km(
                float(a["lat"]),
                float(a["lng"]),
                float(b["lat"]),
                float(b["lng"]),
            )
            if ab_km < 0.18:
                continue

            approx = _triangle_estimate_km(start_lat, start_lng, a, b)

            # Pre-routing filter: keep only pairs whose straight-line triangle
            # is plausibly close to the requested loop size.
            if approx < 0.45 * target_distance_km:
                continue
            if approx > 0.95 * target_distance_km:
                continue

            seed_bonus = 0.0
            if a.get("kind") == "seed_place":
                seed_bonus -= 8.0
            if b.get("kind") == "seed_place":
                seed_bonus -= 8.0

            distance_hint = abs(approx - (0.72 * target_distance_km)) * 10.0
            score_hint = distance_hint - sep + seed_bonus
            pairs.append((a, b, score_hint))

    pairs.sort(key=lambda x: x[2])
    return [(a, b) for a, b, _ in pairs[:_MAX_PAIR_CANDIDATES]]

# ─────────────────────────────────────────────────────────────
# Fallback
# ─────────────────────────────────────────────────────────────

def _fallback_triangle_loop(
    start_lat: float,
    start_lng: float,
    distance_km: float,
) -> dict[str, Any]:
    d = max(distance_km, _MIN_LOOP_KM)
    side_km = d / 3.0
    side_m = side_km * 1000.0

    p0 = [start_lng, start_lat]
    lat1, lng1 = _offset_point(start_lat, start_lng, 0.87 * side_m, 0.50 * side_m)
    lat2, lng2 = _offset_point(start_lat, start_lng, 0.05 * side_m, -0.70 * side_m)
    p1 = [lng1, lat1]
    p2 = [lng2, lat2]
    poly = [p0, p1, p2, p0]

    return {
        "polyline": poly,
        "distance_km": round(d, 2),
        "duration_minutes": int(round((d / 4.5) * 60)),
        "source": "fallback_triangle",
    }


# ─────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────

def _score_loop(
    *,
    polyline: list[list[float]],
    loop_distance_km: float,
    target_distance_km: float,
    a_bearing_deg: float,
    b_bearing_deg: float,
    a_kind: str,
    b_kind: str,
) -> float:
    distance_penalty = abs(loop_distance_km - target_distance_km) * 26.0
    overlap_penalty = _overlap_ratio(polyline) * 100.0

    angular_sep = _angular_sep_deg(a_bearing_deg, b_bearing_deg)
    spread_bonus = -min(angular_sep, 180.0) / 22.0

    seed_bonus = 0.0
    if a_kind == "seed_place":
        seed_bonus -= 3.0
    if b_kind == "seed_place":
        seed_bonus -= 3.0

    return distance_penalty + overlap_penalty + spread_bonus + seed_bonus


# ─────────────────────────────────────────────────────────────
# Candidate construction
# ─────────────────────────────────────────────────────────────

_osrm_semaphore = asyncio.Semaphore(5)


async def _request_osrm_json(
    client: httpx.AsyncClient,
    path_builder,
    mode: str,
) -> dict[str, Any] | None:
    for base_url, profile in get_osrm_candidates(mode):
        url = path_builder(base_url, profile)
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("code") == "Ok":
                data["_resolved_profile"] = profile
                data["_resolved_base_url"] = base_url
                return data
        except Exception as exc:
            if should_fallback_on_error(exc):
                mark_base_url_unhealthy(base_url)
                continue
            break
    return None

async def _build_one_candidate(
    client: httpx.AsyncClient,
    start_lng: float,
    start_lat: float,
    a: dict[str, Any],
    b: dict[str, Any],
    target_distance_km: float,
    mode: str = "walk",
    waypoints: list[tuple[float, float]] | None = None
) -> dict[str, Any] | None:
    
    # OSRM /trip automatically closes the loop back to the start
    # coords = f"{start_lng},{start_lat};{a['lng']},{a['lat']};{b['lng']},{b['lat']}"
    
    coord_list = [f"{start_lng},{start_lat}"]
    if waypoints:
        coord_list.extend([f"{w[0]},{w[1]}" for w in waypoints])
    coord_list.extend([f"{a['lng']},{a['lat']}", f"{b['lng']},{b['lat']}"])
    coords = ";".join(coord_list)

    async with _osrm_semaphore:
        try:
            data = await _request_osrm_json(
                client,
                lambda base_url, profile: (
                    f"{base_url.rstrip('/')}/trip/v1/{profile}/{coords}"
                    "?roundtrip=true&source=first&destination=last"
                    "&geometries=geojson&overview=full&steps=false"
                ),
                mode,
            )

            if not data or not data.get("trips"):
                return None

            trip = data["trips"][0]
            total_distance = float(trip["distance"]) / 1000.0

            # Hard reject candidates that are too far from requested distance
            if total_distance < 0.70 * target_distance_km:
                return None
            if total_distance > 1.35 * target_distance_km:
                return None

            coords_out = trip.get("geometry", {}).get("coordinates", [])
            polyline = [[float(c[0]), float(c[1])] for c in coords_out]
            total_duration = int(round(float(trip["duration"]) / 60.0))

            score = _score_loop(
                polyline=polyline,
                loop_distance_km=total_distance,
                target_distance_km=target_distance_km,
                a_bearing_deg=float(a["bearing_deg"]),
                b_bearing_deg=float(b["bearing_deg"]),
                a_kind=str(a.get("kind", "")),
                b_kind=str(b.get("kind", "")),
            )

            return {
                "polyline": polyline,
                "distance_km": round(total_distance, 2),
                "duration_minutes": total_duration,
                "source": f"osrm_{data['_resolved_profile']}_trip_loop",
                "_score": score,
                "_anchors": [a["name"], b["name"]],
            }
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

async def generate_loop_variants(
    start_lng: float,
    start_lat: float,
    distance_km: float,
    count: int = 3,
    mode: str = "walk",
    waypoints: list[tuple[float, float]] | None = None
) -> list[dict[str, Any]]:
    target = max(distance_km, _MIN_LOOP_KM)
    anchors = _generate_candidate_anchors(start_lat, start_lng, target)
    pairs = _candidate_anchor_pairs(start_lat, start_lng, anchors, target)

    if not pairs:
        return [_fallback_triangle_loop(start_lat, start_lng, target)]

    async with httpx.AsyncClient(timeout=ROUTE_TIMEOUT_S) as client:
        tasks = [
            _build_one_candidate(client, start_lng, start_lat, a, b, target, mode, waypoints)
            for a, b in pairs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    valid = [r for r in results if r is not None]
    if not valid:
        return [_fallback_triangle_loop(start_lat, start_lng, target)]

    valid.sort(key=lambda x: float(x["_score"]))

    out: list[dict[str, Any]] = []
    for item in valid[: max(1, count)]:
        out.append(
            {
                "polyline": item["polyline"],
                "distance_km": item["distance_km"],
                "duration_minutes": item["duration_minutes"],
                "source": item["source"],
            }
        )

    return out

async def generate_a2b(
    start_lng: float,
    start_lat: float,
    end_lng: float,
    end_lat: float,
    mode: str = "walk",
    waypoints: list[tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    # We request alternatives=true to give the user options
    coord_list = [f"{start_lng},{start_lat}"]
    if waypoints:
        coord_list.extend([f"{w[0]},{w[1]}" for w in waypoints])
    coord_list.append(f"{end_lng},{end_lat}")
    coords_str = ";".join(coord_list)

    async with httpx.AsyncClient(timeout=ROUTE_TIMEOUT_S) as client:
        try:
            data = await _request_osrm_json(
                client,
                lambda base_url, profile: (
                    f"{base_url.rstrip('/')}/route/v1/{profile}/{coords_str}"
                    "?geometries=geojson&overview=full&steps=false&alternatives=true"
                ),
                mode,
            )

            if not data or not data.get("routes"):
                return []

            out = []
            for r in data["routes"]:
                polyline = [[float(c[0]), float(c[1])] for c in r["geometry"]["coordinates"]]
                dist_km = float(r["distance"]) / 1000.0
                dur_min = int(round(float(r["duration"]) / 60.0))

                out.append({
                    "polyline": polyline,
                    "distance_km": round(dist_km, 2),
                    "duration_minutes": dur_min,
                    "source": f"osrm_{data['_resolved_profile']}_a2b",
                })
            return out
        except Exception:
            return []
