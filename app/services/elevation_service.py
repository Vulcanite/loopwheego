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

import httpx

from app.utils.geo import haversine_m

ELEVATION_API_URL = os.getenv("ELEVATION_API_URL", "http://localhost:2999/v1/srtm30m")
ELEVATION_TIMEOUT_S = float(os.getenv("ELEVATION_TIMEOUT_S", "5.0"))
ELEVATION_SAMPLE_SPACING_M = float(os.getenv("ELEVATION_SAMPLE_SPACING_M", "50"))
ELEVATION_BATCH_SIZE = int(os.getenv("ELEVATION_BATCH_SIZE", "80"))
ELEVATION_GAIN_THRESHOLD_M = float(os.getenv("ELEVATION_GAIN_THRESHOLD_M", "1.5"))

logger = logging.getLogger(__name__)


def _resample_polyline(
    polyline: list,
    spacing_m: float,
) -> list[tuple[float, float]]:
    """Resample a [lng, lat] polyline at a fixed distance interval."""
    if not polyline:
        return []

    coords = [(float(pt[0]), float(pt[1])) for pt in polyline]
    if len(coords) == 1 or spacing_m <= 0:
        return coords

    out: list[tuple[float, float]] = [coords[0]]
    distance_since_last = 0.0
    current_start = coords[0]

    for current_end in coords[1:]:
        start_lng, start_lat = current_start
        end_lng, end_lat = current_end
        segment_len_m = haversine_m(start_lat, start_lng, end_lat, end_lng)

        if segment_len_m <= 0.01:
            current_start = current_end
            continue

        while distance_since_last + segment_len_m >= spacing_m:
            remaining_m = spacing_m - distance_since_last
            ratio = remaining_m / segment_len_m
            interp_lng = start_lng + (end_lng - start_lng) * ratio
            interp_lat = start_lat + (end_lat - start_lat) * ratio
            interpolated = (interp_lng, interp_lat)
            out.append(interpolated)

            start_lng, start_lat = interpolated
            segment_len_m -= remaining_m
            distance_since_last = 0.0

        distance_since_last += segment_len_m
        current_start = current_end

    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out


async def _fetch_elevation_batch(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
) -> list[float] | None:
    """
    Query OpenTopoData with a batch of (lng, lat) points.

    NOTE: polyline is stored as [lng, lat] (GeoJSON/OSRM convention).
    OpenTopoData expects lat,lng — coordinates are swapped here.

    Returns list of elevation values in metres, or None on any failure.
    """
    if not points:
        return []

    locations = "|".join(f"{lat:.5f},{lng:.5f}" for lng, lat in points)
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


async def _fetch_elevations(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
) -> list[float] | None:
    out: list[float] = []
    for idx in range(0, len(points), ELEVATION_BATCH_SIZE):
        batch = points[idx : idx + ELEVATION_BATCH_SIZE]
        elevations = await _fetch_elevation_batch(client, batch)
        if elevations is None:
            logger.warning(
                "Elevation batch failed: batch_size=%d sample_points=%d",
                len(batch),
                len(points),
            )
            return None
        out.extend(elevations)
    return out


def _smooth_elevations(elevations: list[float]) -> list[float]:
    if len(elevations) < 3:
        return elevations

    smoothed: list[float] = []
    for idx in range(len(elevations)):
        window = elevations[max(0, idx - 1) : min(len(elevations), idx + 2)]
        smoothed.append(sum(window) / len(window))
    return smoothed


def _compute_elevation_gain(elevations: list[float]) -> float:
    """Sum of all uphill segments in metres. Descents ignored."""
    gain = 0.0
    for i in range(1, len(elevations)):
        delta = elevations[i] - elevations[i - 1]
        if delta > ELEVATION_GAIN_THRESHOLD_M:
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


async def _enrich_route_with_effort(
    client: httpx.AsyncClient,
    polyline: list,
    distance_km: float,
    mode: str,
) -> tuple[float | None, str]:
    """
    Returns (elevation_gain_m, effort_label).

    elevation_gain_m is None if the elevation API was unreachable.
    effort_label is always returned — falls back to distance-only if no elevation.
    """
    sampled = _resample_polyline(polyline, ELEVATION_SAMPLE_SPACING_M)
    elevations = await _fetch_elevations(client, sampled)

    if elevations is None:
        label = _classify_effort(distance_km, 0.0, mode)
        return None, label

    smoothed_elevations = _smooth_elevations(elevations)
    gain_m = _compute_elevation_gain(smoothed_elevations)
    label = _classify_effort(distance_km, gain_m, mode)
    return gain_m, label


async def enrich_routes_with_effort(
    routes: list[dict],
    mode: str,
) -> list[tuple[float | None, str]]:
    """
    Enrich multiple routes concurrently.

    routes: list of dicts with 'polyline' and 'distance_km' keys
            (same shape as route_generator output).

    Returns list of (elevation_gain_m, effort_label) in same order.
    """
    async with httpx.AsyncClient(timeout=ELEVATION_TIMEOUT_S) as client:
        tasks = [
            _enrich_route_with_effort(client, r["polyline"], float(r["distance_km"]), mode)
            for r in routes
        ]
        return list(await asyncio.gather(*tasks))
