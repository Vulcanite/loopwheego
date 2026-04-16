import asyncio
import io
import os
import uuid
from typing import Annotated

import gpxpy
import gpxpy.gpx
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.models.route import GPXRequest, MultiRouteResponse, POIDiscoveryRequest, RouteRequest, RouteResponse
from app.models.poi import POI

from app.services import overpass
from app.services.elevation_service import enrich_routes_with_effort
from app.services.external_endpoints import (
    get_nominatim_base_urls,
    mark_base_url_unhealthy,
    should_fallback_on_error,
)
from app.services.llm import LLMService
from app.services import route_generator

router = APIRouter()

_llm_singleton = LLMService()

ENABLE_POIS = os.getenv("ENABLE_POIS", "false").lower() == "true"
ENABLE_LLM_NARRATION = os.getenv("ENABLE_LLM_NARRATION", "false").lower() == "true"
WALK_SPEED_KMH = 4.5
CYCLE_SPEED_KMH = 10.0
MIN_DISTANCE_KM = 3.0
MAX_WALK_DISTANCE_KM = 50.0
MAX_CYCLE_DISTANCE_KM = 100.0


def get_llm_service() -> LLMService:
    return _llm_singleton


def _route_signature(route: dict) -> tuple:
    polyline = route.get("polyline") or []
    if not polyline:
        return (round(float(route.get("distance_km", 0.0)), 2), "empty")

    sample_indexes = sorted({0, len(polyline) // 3, (2 * len(polyline)) // 3, len(polyline) - 1})
    sampled_points = tuple(
        (round(float(polyline[idx][0]), 5), round(float(polyline[idx][1]), 5))
        for idx in sample_indexes
    )
    return (round(float(route.get("distance_km", 0.0)), 2), sampled_points)


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for route in routes:
        sig = _route_signature(route)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(route)
    return out


def _clamp_fitness_distance(distance_km: float, mode: str) -> float:
    max_distance = MAX_CYCLE_DISTANCE_KM if mode == "cycle" else MAX_WALK_DISTANCE_KM
    return max(MIN_DISTANCE_KM, min(max_distance, distance_km))


def _fitness_target_distances(distance_km: float, mode: str) -> list[float]:
    factors = [0.72, 1.0, 1.28] if mode == "walk" else [0.70, 1.0, 1.35]
    targets: list[float] = []
    seen: set[float] = set()

    for factor in factors:
        target = round(_clamp_fitness_distance(distance_km * factor, mode), 2)
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)

    requested = round(_clamp_fitness_distance(distance_km, mode), 2)
    if requested not in seen:
        targets.append(requested)
    return targets


def _pick_route_pairs(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
    requested_distance_km: float,
    limit: int = 3,
) -> list[tuple[dict, tuple[float | None, str]]]:
    paired = list(zip(routes, effort_results))
    paired.sort(key=lambda item: (abs(float(item[0]["distance_km"]) - requested_distance_km), float(item[0]["distance_km"])))

    selected: list[tuple[dict, tuple[float | None, str]]] = []
    used_sigs: set[tuple] = set()
    used_labels: set[str] = set()

    for target_label in ("Easy", "Moderate", "Hard"):
        for route, effort in paired:
            label = effort[1]
            sig = _route_signature(route)
            if sig in used_sigs or label != target_label:
                continue
            selected.append((route, effort))
            used_sigs.add(sig)
            used_labels.add(label)
            break
        if len(selected) >= limit:
            return selected

    for route, effort in paired:
        sig = _route_signature(route)
        label = effort[1]
        if sig in used_sigs:
            continue
        if label not in used_labels:
            selected.append((route, effort))
            used_sigs.add(sig)
            used_labels.add(label)
        if len(selected) >= limit:
            return selected

    for route, effort in paired:
        sig = _route_signature(route)
        if sig in used_sigs:
            continue
        selected.append((route, effort))
        used_sigs.add(sig)
        if len(selected) >= limit:
            return selected

    return selected


async def _generate_fitness_loop_routes(
    start_lng: float,
    start_lat: float,
    distance_km: float,
    mode: str,
    waypoints: list[tuple[float, float]] | None,
) -> tuple[list[dict], list[tuple[float | None, str]]]:
    targets = _fitness_target_distances(distance_km, mode)
    tasks = [
        route_generator.generate_loop_variants(
            start_lng,
            start_lat,
            target,
            count=2 if abs(target - distance_km) < 0.01 else 1,
            mode=mode,
            waypoints=waypoints,
        )
        for target in targets
    ]

    generated_groups = await asyncio.gather(*tasks)
    candidates = _dedupe_routes([route for group in generated_groups for route in group])
    if not candidates:
        return [], []

    effort_results = await enrich_routes_with_effort(candidates, mode=mode)
    selected_pairs = _pick_route_pairs(candidates, effort_results, requested_distance_km=distance_km, limit=3)
    return [route for route, _ in selected_pairs], [effort for _, effort in selected_pairs]


async def _build_route_responses(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
) -> list[RouteResponse]:
    out: list[RouteResponse] = []
    for idx, (route, (elevation_gain_m, effort_label)) in enumerate(zip(routes, effort_results), start=1):
        polyline = route["polyline"]
        distance_km = float(route["distance_km"])
        duration_minutes = int(route["duration_minutes"])
        source = str(route.get("source", "unknown"))
        pl_tuples = [(float(pt[0]), float(pt[1])) for pt in polyline]
        print(
            "Generated route "
            f"{idx}: source={source} "
            f"distance_km={distance_km:.2f} "
            f"duration_minutes={duration_minutes} "
            f"elevation_gain_m={'None' if elevation_gain_m is None else round(float(elevation_gain_m), 1)} "
            f"label={effort_label}"
        )
        out.append(
            RouteResponse(
                polyline=pl_tuples,
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                pois=[],
                source=source,
                elevation_gain_m=elevation_gain_m,
                effort_label=effort_label,
                label=effort_label,
            )
        )
    return out


async def _reverse_geocode_name(lng: float, lat: float) -> str:
    async with httpx.AsyncClient(timeout=8.0) as client:
        for base_url in get_nominatim_base_urls():
            try:
                r = await client.get(
                    f"{base_url}/reverse",
                    params={
                        "lat": lat,
                        "lon": lng,
                        "format": "json",
                    },
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "LoopWheeGo/1.0",
                    },
                )
                r.raise_for_status()
                data = r.json()
                name = data.get("display_name")
                if isinstance(name, str) and name.strip():
                    return name.strip()[:240]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                if should_fallback_on_error(exc):
                    mark_base_url_unhealthy(base_url)
                    continue
                break
    return "your starting point"


async def _build_pois(
    polyline: list[list[float]],
    start_lng: float,
    start_lat: float,
    distance_km: float,
    llm: LLMService,
) -> list[POI]:
    
    if not ENABLE_POIS:
        return []

    raw_pois = await overpass.fetch_pois_along_route(polyline, max_pois=5)
    print(f"-> Overpass returned {len(raw_pois)} raw POIs.")

    if not raw_pois:
        return []

    enriched = raw_pois
    if ENABLE_LLM_NARRATION:
        start_name = await _reverse_geocode_name(start_lng, start_lat)
        route_context = {
            "distance_km": distance_km,
            "start_location_name": start_name,
        }
        
        try:
            enriched = await llm.narrate_pois(raw_pois, route_context)
        except Exception as e:
            print(f"-> ERROR IN LLM CALL: {e}")
    else:
        enriched = [
            {**p, "narration": "", "duration_suggested_minutes": 5}
            for p in raw_pois
        ]

    pois_out: list[POI] = []
    for p in enriched:
        try:
            dur = int(p.get("duration_suggested_minutes", 5))
        except (TypeError, ValueError):
            dur = 5

        narr = p.get("narration", "")
        if not isinstance(narr, str):
            narr = ""

        pois_out.append(
            POI(
                id=str(uuid.uuid4()),
                name=str(p["name"]),
                lat=float(p["lat"]),
                lng=float(p["lng"]),
                category=str(p["category"]),
                narration=narr,
                duration_suggested_minutes=dur,
            )
        )
        
    return pois_out


@router.post("/discover-pois", response_model=list[POI])
async def discover_pois(
    body: POIDiscoveryRequest,
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> list[POI]:
    try:
        pois = await _build_pois(
            polyline=body.polyline,
            start_lng=body.start_lng,
            start_lat=body.start_lat,
            distance_km=body.distance_km,
            llm=llm,
        )
        return pois
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not discover places for this route.",
        ) from exc

@router.post("/generate-variants", response_model=MultiRouteResponse)
async def generate_route_variants(
    body: RouteRequest,
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> MultiRouteResponse:
    try:
        # 1. Branching based on Route Type
        route_type = getattr(body, "routeType", "loop")
        mode = getattr(body, "mode", "walk")
        app_mode = getattr(body, "appMode", "fitness")

        target_distance_km = body.distance_km
        if route_type != "a2b":
            if app_mode == "explorer":
                if body.target_duration_minutes is None:
                    raise HTTPException(status_code=400, detail="Explorer routes require target_duration_minutes.")
                speed = CYCLE_SPEED_KMH if mode == "cycle" else WALK_SPEED_KMH
                target_distance_km = max((speed * body.target_duration_minutes) / 60.0, 1.0)
            elif target_distance_km is None:
                raise HTTPException(status_code=400, detail="Fitness routes require distance_km.")
            else:
                max_distance = MAX_CYCLE_DISTANCE_KM if mode == "cycle" else MAX_WALK_DISTANCE_KM
                if target_distance_km < MIN_DISTANCE_KM:
                    raise HTTPException(
                        status_code=400,
                        detail=f"distance_km must be at least {MIN_DISTANCE_KM:g} for fitness routes.",
                    )
                if target_distance_km > max_distance:
                    raise HTTPException(
                        status_code=400,
                        detail=f"distance_km cannot exceed {max_distance:g} for mode={mode}.",
                    )

        effort_results: list[tuple[float | None, str]] | None = None

        if route_type == "a2b":
            # For A to B, we need end coordinates
            end_lng = getattr(body, "end_lng", None)
            end_lat = getattr(body, "end_lat", None)
            if end_lng is None or end_lat is None:
                raise HTTPException(status_code=400, detail="A to B requires an end point.")
            
            routes = await route_generator.generate_a2b(
                body.start_lng, body.start_lat, end_lng, end_lat, mode=mode, waypoints=body.waypoints
            )
        elif app_mode == "fitness":
            routes, effort_results = await _generate_fitness_loop_routes(
                body.start_lng,
                body.start_lat,
                float(target_distance_km),
                mode=mode,
                waypoints=body.waypoints,
            )
        else:
            # Default to Loop generation
            routes = await route_generator.generate_loop_variants(
                body.start_lng, body.start_lat, float(target_distance_km), count=3, mode=mode, waypoints=body.waypoints
            )
            
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Route generation failed. Try again.",
        ) from exc

    if effort_results is None:
        effort_results = await enrich_routes_with_effort(routes, mode=mode)

    return MultiRouteResponse(routes=await _build_route_responses(routes, effort_results))


@router.post("/export/gpx")
async def export_gpx(body: GPXRequest) -> StreamingResponse:
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx_track.name = body.route_name
    segment = gpxpy.gpx.GPXTrackSegment()

    for lng, lat in body.polyline:
        segment.points.append(
            gpxpy.gpx.GPXTrackPoint(latitude=float(lat), longitude=float(lng))
        )

    gpx_track.segments.append(segment)
    gpx.tracks.append(gpx_track)

    for poi in body.pois:
        wp = gpxpy.gpx.GPXWaypoint(
            latitude=float(poi.lat),
            longitude=float(poi.lng),
            name=poi.name,
            description=poi.narration or "",
        )
        gpx.waypoints.append(wp)

    xml = gpx.to_xml()
    buf = io.BytesIO(xml.encode("utf-8"))
    buf.seek(0)

    headers = {
        "Content-Disposition": 'attachment; filename="loopwheego_route.gpx"',
    }

    return StreamingResponse(
        buf,
        media_type="application/gpx+xml",
        headers=headers,
    )
