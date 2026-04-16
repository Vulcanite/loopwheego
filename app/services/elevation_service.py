"""
Elevation enrichment service.

Fetches SRTM30m elevations from OpenTopoData for polyline points,
computes cumulative elevation gain, and classifies route effort.

Degrades gracefully if the elevation API is unavailable — effort_label
is always returned (falls back to distance-only), elevation_gain_m is
None when the API is unreachable.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

ELEVATION_API_URL = os.getenv("ELEVATION_API_URL", "http://localhost:2999/v1/srtm30m")
ELEVATION_TIMEOUT_S = float(os.getenv("ELEVATION_TIMEOUT_S", "5.0"))
MAX_ELEVATION_SAMPLES = int(os.getenv("MAX_ELEVATION_SAMPLES", "60"))

logger = logging.getLogger(__name__)


def _subsample_polyline(
    polyline: list,
    max_points: int,
) -> list[tuple[float, float]]:
    """Evenly subsample polyline to at most max_points coords."""
    if len(polyline) <= max_points:
        return [(float(pt[0]), float(pt[1])) for pt in polyline]
    step = len(polyline) // max_points
    return [(float(polyline[i][0]), float(polyline[i][1])) for i in range(0, len(polyline), step)]


async def _fetch_elevations(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
) -> list[float] | None:
    """
    Query OpenTopoData with a batch of (lng, lat) points.

    NOTE: polyline is stored as [lng, lat] (GeoJSON/OSRM convention).
    OpenTopoData expects lat,lng — coordinates are swapped here.

    Returns list of elevation values in metres, or None on any failure.
    """
    # Swap lng,lat → lat,lng for the API
    locations = "|".join(f"{lat},{lng}" for lng, lat in points)
    try:
        resp = await client.get(
            ELEVATION_API_URL,
            params={"locations": locations},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            logger.warning("Elevation API returned status: %s", data.get("status"))
            return None
        return [r["elevation"] for r in data["results"]]
    except Exception as exc:
        logger.warning("Elevation API unavailable: %s", exc)
        return None


def _compute_elevation_gain(elevations: list[float]) -> float:
    """Sum of all uphill segments in metres. Descents ignored."""
    gain = 0.0
    for i in range(1, len(elevations)):
        delta = elevations[i] - elevations[i - 1]
        if delta > 0:
            gain += delta
    return gain


def _classify_effort(
    distance_km: float,
    elevation_gain_m: float,
    mode: str,
) -> str:
    """
    Adjusted Effort Distance (AED) using Naismith's Rule:
      walk:  10m gain ≈ 100m flat  → gain_factor = 10.0
      cycle:  10m gain ≈  60m flat  → gain_factor =  6.0

    Walk thresholds:  AED < 5  → Easy, < 10 → Moderate, else Hard
    Cycle thresholds: AED < 12 → Easy, < 25 → Moderate, else Hard
    """
    gain_factor = 10.0 if mode == "walk" else 6.0
    aed_km = distance_km + (elevation_gain_m / 1000.0) * gain_factor

    if mode == "walk":
        if aed_km < 5.0:
            return "Easy"
        if aed_km < 10.0:
            return "Moderate"
        return "Hard"
    else:  # cycle
        if aed_km < 12.0:
            return "Easy"
        if aed_km < 25.0:
            return "Moderate"
        return "Hard"


async def enrich_route_with_effort(
    client: httpx.AsyncClient,
    polyline: list,
    distance_km: float,
    mode: str,
) -> tuple[Optional[float], str]:
    """
    Returns (elevation_gain_m, effort_label).

    elevation_gain_m is None if the elevation API was unreachable.
    effort_label is always returned — falls back to distance-only if no elevation.
    """
    sampled = _subsample_polyline(polyline, MAX_ELEVATION_SAMPLES)
    elevations = await _fetch_elevations(client, sampled)

    if elevations is None:
        # Graceful degradation: classify from distance only
        label = _classify_effort(distance_km, 0.0, mode)
        return None, label

    gain_m = _compute_elevation_gain(elevations)
    label = _classify_effort(distance_km, gain_m, mode)
    return gain_m, label


async def enrich_routes_with_effort(
    routes: list[dict],
    mode: str,
) -> list[tuple[Optional[float], str]]:
    """
    Enrich multiple routes concurrently.

    routes: list of dicts with 'polyline' and 'distance_km' keys
            (same shape as route_generator output).

    Returns list of (elevation_gain_m, effort_label) in same order.
    """
    async with httpx.AsyncClient(timeout=ELEVATION_TIMEOUT_S) as client:
        tasks = [
            enrich_route_with_effort(client, r["polyline"], float(r["distance_km"]), mode)
            for r in routes
        ]
        return list(await asyncio.gather(*tasks))
