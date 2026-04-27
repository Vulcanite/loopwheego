import asyncio
import io
import os
import uuid

import gpxpy
import gpxpy.gpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.route import GPXRequest, MultiRouteResponse, POIDiscoveryRequest, RouteRequest, RouteResponse
from app.models.poi import POI

from app.services import overpass
from app.services import cached_places
from app.services.elevation_service import enrich_routes_with_effort
from app.services import route_generator

router = APIRouter()

ENABLE_POIS = os.getenv("ENABLE_POIS", "false").lower() == "true"
WALK_SPEED_KMH = 4.5
CYCLE_SPEED_KMH = 10.0
MIN_DISTANCE_KM = 3.0
MAX_WALK_DISTANCE_KM = 50.0
MAX_CYCLE_DISTANCE_KM = 100.0
MAX_FITNESS_ROUTES = 4
ROUTE_DUPLICATE_SIMILARITY_THRESHOLD = 0.88
ROUTE_SELECTION_SIMILARITY_THRESHOLD = 0.82


def _target_distance_for_duration(mode: str, target_duration_minutes: int) -> float:
    speed = CYCLE_SPEED_KMH if mode == "cycle" else WALK_SPEED_KMH
    return max((speed * target_duration_minutes) / 60.0, 1.0)


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


def _route_point_signature(
    route: dict,
    *,
    max_points: int = 180,
    precision: int = 4,
) -> set[tuple[float, float]]:
    polyline = route.get("polyline") or []
    if not polyline:
        return set()

    step = max(1, len(polyline) // max_points)
    sampled = {
        (round(float(polyline[idx][0]), precision), round(float(polyline[idx][1]), precision))
        for idx in range(0, len(polyline), step)
    }
    last = polyline[-1]
    sampled.add((round(float(last[0]), precision), round(float(last[1]), precision)))
    return sampled


def _route_similarity_ratio(route_a: dict, route_b: dict) -> float:
    sig_a = _route_point_signature(route_a)
    sig_b = _route_point_signature(route_b)
    if not sig_a or not sig_b:
        return 0.0
    shared = len(sig_a & sig_b)
    baseline = min(len(sig_a), len(sig_b))
    if baseline <= 0:
        return 0.0
    return shared / baseline


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for route in routes:
        sig = _route_signature(route)
        if sig in seen:
            continue
        if any(_route_similarity_ratio(route, kept) >= ROUTE_DUPLICATE_SIMILARITY_THRESHOLD for kept in out):
            continue
        seen.add(sig)
        out.append(route)
    return out


def _clamp_fitness_distance(distance_km: float, mode: str) -> float:
    max_distance = MAX_CYCLE_DISTANCE_KM if mode == "cycle" else MAX_WALK_DISTANCE_KM
    return max(MIN_DISTANCE_KM, min(max_distance, distance_km))


def _fitness_target_distances(distance_km: float, mode: str) -> list[float]:
    factors = (
        [0.62, 0.74, 0.86, 0.94, 1.0, 1.06, 1.14, 1.26, 1.40]
        if mode == "walk"
        else [0.58, 0.70, 0.84, 0.93, 1.0, 1.07, 1.16, 1.30, 1.48]
    )
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


def _fitness_variant_count_for_target(requested_distance_km: float, target_distance_km: float) -> int:
    ratio_delta = abs(target_distance_km - requested_distance_km) / max(requested_distance_km, 0.1)
    if ratio_delta < 0.015:
        return 3
    if ratio_delta <= 0.12:
        return 2
    return 1


def _fitness_selection_score(
    route: dict,
    elevation_gain_m: float | None,
    requested_distance_km: float,
    mode: str,
) -> float:
    distance_km = float(route.get("distance_km", 0.0))
    effort_score = _route_effort_score(route, elevation_gain_m, mode)
    distance_penalty = abs(distance_km - requested_distance_km) * 2.4
    effort_penalty = abs(effort_score - requested_distance_km) * 0.9
    overshoot_penalty = max(0.0, distance_km - requested_distance_km) * 0.35
    return distance_penalty + effort_penalty + overshoot_penalty


def _route_effort_score(
    route: dict,
    elevation_gain_m: float | None,
    mode: str,
) -> float:
    gain_factor = 10.0 if mode == "walk" else 6.0
    distance_km = float(route.get("distance_km", 0.0))
    gain_km = (float(elevation_gain_m) / 1000.0) if elevation_gain_m is not None else 0.0
    return distance_km + gain_km * gain_factor


def _pick_route_pairs(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
    requested_distance_km: float,
    mode: str,
    limit: int = 3,
) -> list[tuple[dict, tuple[float | None, str]]]:
    paired = list(zip(routes, effort_results))
    if len(paired) <= limit:
        return paired

    scored = [
        (
            route,
            effort,
            _fitness_selection_score(route, effort[0], requested_distance_km, mode),
        )
        for route, effort in paired
    ]
    scored.sort(
        key=lambda item: (
            item[2],
            abs(float(item[0]["distance_km"]) - requested_distance_km),
            _route_effort_score(item[0], item[1][0], mode),
        )
    )

    shortlist_size = min(len(scored), max(limit + 3, 8))
    shortlist = scored[:shortlist_size]
    distance_tolerance_km = max(0.75, requested_distance_km * 0.12)
    acceptable = [
        (route, effort, selection_score)
        for route, effort, selection_score in shortlist
        if abs(float(route["distance_km"]) - requested_distance_km) <= distance_tolerance_km
    ]

    selection_pool = acceptable if acceptable else shortlist[: min(3, len(shortlist))]

    selected: list[tuple[dict, tuple[float | None, str]]] = []
    backup: list[tuple[dict, tuple[float | None, str]]] = []
    diversity_rejected = 0
    for route, effort, _ in selection_pool:
        if any(_route_similarity_ratio(route, chosen_route) >= ROUTE_SELECTION_SIMILARITY_THRESHOLD for chosen_route, _ in selected):
            diversity_rejected += 1
            backup.append((route, effort))
            continue
        selected.append((route, effort))
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for route, effort in backup:
            selected.append((route, effort))
            if len(selected) >= limit:
                break

    print(
        "fitness_route_ranking: "
        f"requested_km={requested_distance_km:.2f} "
        f"candidates={len(scored)} "
        f"shortlist={shortlist_size} "
        f"distance_tolerance_km={distance_tolerance_km:.2f} "
        f"acceptable={len(acceptable)} "
        f"diversity_rejected={diversity_rejected} "
        f"top={[{'distance_km': round(float(route['distance_km']), 2), 'score': round(selection_score, 2)} for route, _, selection_score in scored[:min(5, len(scored))]]}"
    )
    return selected[:limit]


def _apply_relative_effort_labels(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
    mode: str,
) -> list[tuple[float | None, str]]:
    if not routes:
        return []
    if len(routes) == 1:
        elevation_gain_m, _ = effort_results[0]
        return [(elevation_gain_m, "Balanced")]

    ranked = sorted(
        [
            (
                idx,
                _route_effort_score(route, effort[0], mode),
                effort[0],
            )
            for idx, (route, effort) in enumerate(zip(routes, effort_results))
        ],
        key=lambda item: item[1],
    )

    count = len(ranked)
    easy_count = max(1, round(count / 3))
    hard_count = max(1, round(count / 3))
    medium_start = easy_count
    hard_start = max(medium_start, count - hard_count)

    labels_by_idx: dict[int, tuple[float | None, str]] = {}
    for rank, (idx, score, elevation_gain_m) in enumerate(ranked):
        if rank < medium_start:
            label = "Easier"
        elif rank >= hard_start:
            label = "Tougher"
        else:
            label = "Balanced"
        labels_by_idx[idx] = (elevation_gain_m, label)

    labeled = [labels_by_idx[idx] for idx in range(len(routes))]
    print(
        "fitness_relative_effort_labels: "
        f"scores={[round(score, 2) for _, score, _ in ranked]}"
    )
    return labeled


def _sort_routes_by_effort(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
    mode: str,
) -> tuple[list[dict], list[tuple[float | None, str]]]:
    paired = list(zip(routes, effort_results))
    paired.sort(
        key=lambda item: (
            _route_effort_score(item[0], item[1][0], mode),
            abs(float(item[0].get("distance_km", 0.0))),
        )
    )
    return [route for route, _ in paired], [effort for _, effort in paired]


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
            count=_fitness_variant_count_for_target(distance_km, target),
            mode=mode,
            waypoints=waypoints,
        )
        for target in targets
    ]

    generated_groups = await asyncio.gather(*tasks)
    raw_candidates = [route for group in generated_groups for route in group]
    candidates = _dedupe_routes(raw_candidates)
    if not candidates:
        return [], []

    effort_results = await enrich_routes_with_effort(candidates, mode=mode)
    selected_pairs = _pick_route_pairs(
        candidates,
        effort_results,
        requested_distance_km=distance_km,
        mode=mode,
        limit=MAX_FITNESS_ROUTES,
    )
    selected_routes = [route for route, _ in selected_pairs]
    selected_efforts = [effort for _, effort in selected_pairs]
    relabeled_efforts = _apply_relative_effort_labels(selected_routes, selected_efforts, mode)
    selected_routes, relabeled_efforts = _sort_routes_by_effort(selected_routes, relabeled_efforts, mode)
    print(
        "fitness_loop_routes_selected: "
        f"requested_km={distance_km:.2f} "
        f"raw_candidates={len(raw_candidates)} "
        f"candidates={len(candidates)} "
        f"selected={len(selected_routes)} "
        f"distances={[round(float(route['distance_km']), 2) for route in selected_routes]} "
        f"labels={[label for _, label in relabeled_efforts]}"
    )
    return selected_routes, relabeled_efforts


async def _build_route_responses(
    routes: list[dict],
    effort_results: list[tuple[float | None, str]],
    route_pois: list[list[POI]] | None = None,
    app_mode: str = "fitness",
) -> list[RouteResponse]:
    out: list[RouteResponse] = []
    for idx, (route, (elevation_gain_m, effort_label)) in enumerate(zip(routes, effort_results), start=1):
        polyline = route["polyline"]
        distance_km = float(route["distance_km"])
        duration_minutes = int(route["duration_minutes"])
        source = str(route.get("source", "unknown"))
        pl_tuples = [(float(pt[0]), float(pt[1])) for pt in polyline]
        pois = route_pois[idx - 1] if route_pois and idx - 1 < len(route_pois) else []
        response_elevation_gain_m = None if app_mode == "explorer" else elevation_gain_m
        response_effort_label = None if app_mode == "explorer" else effort_label
        print(
            "Generated route "
            f"{idx}: source={source} "
            f"distance_km={distance_km:.2f} "
            f"duration_minutes={duration_minutes} "
            f"elevation_gain_m={'None' if response_elevation_gain_m is None else round(float(response_elevation_gain_m), 1)} "
            f"label={response_effort_label}"
        )
        out.append(
            RouteResponse(
                polyline=pl_tuples,
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                pois=pois,
                source=source,
                elevation_gain_m=response_elevation_gain_m,
                effort_label=response_effort_label,
                label=response_effort_label,
            )
        )
    return out


async def _build_pois(
    polyline: list[list[float]],
) -> list[POI]:
    
    if not ENABLE_POIS:
        return []

    raw_pois = await overpass.fetch_pois_along_route(polyline, max_pois=5)
    print(f"-> Overpass returned {len(raw_pois)} raw POIs.")

    if not raw_pois:
        return []

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

def _explorer_poi_score(places: list[dict]) -> float:
    if not places:
        return 0.0

    prominence = sum(float(place.get("_prominence", 0)) for place in places)
    diversity = len({str(place.get("category", "")) for place in places})
    corridor_penalty = sum(float(place.get("_route_dist_km", 0.0)) for place in places)
    return prominence + diversity * 2.0 - corridor_penalty * 8.0


def _build_explorer_route_pois(
    routes: list[dict],
    poi_categories: list[str] | None,
    *,
    loop_mode: bool = False,
) -> tuple[list[dict], list[list[POI]]]:
    ranked_routes: list[tuple[float, dict, list[POI]]] = []
    nearby_corridor_km = 0.25

    for route in routes:
        source = str(route.get("source", "unknown"))
        polyline = route.get("polyline") or []
        if loop_mode:
            nearby_places = cached_places.pick_places_for_loop_area(
                polyline,
                categories=poi_categories,
                limit=8,
            )
        else:
            nearby_places = cached_places.pick_places_along_polyline(
                polyline,
                categories=poi_categories,
                limit=8,
                corridor_km=nearby_corridor_km,
            )
        combined = cached_places.places_to_pois(nearby_places)
        score = _explorer_poi_score(nearby_places)
        print(
            "explorer_route_pois: "
            f"source={source} "
            f"mode={'loop_area' if loop_mode else 'route_corridor'} "
            f"nearby={[place['name'] for place in nearby_places]} "
            f"total={len(combined)} "
            f"score={score:.2f}"
        )
        ranked_routes.append((score, route, combined))

    ranked_routes.sort(
        key=lambda item: (
            -item[0],
            abs(float(item[1].get("distance_km", 0.0))),
        )
    )
    return [route for _, route, _ in ranked_routes], [pois for _, _, pois in ranked_routes]


async def _generate_explorer_loop_routes(
    start_lng: float,
    start_lat: float,
    target_distance_km: float,
    mode: str,
    poi_categories: list[str] | None,
    user_waypoints: list[tuple[float, float]] | None,
) -> tuple[list[dict], list[list[POI]]]:
    routes = await route_generator.generate_loop_variants(
        start_lng,
        start_lat,
        float(target_distance_km),
        count=3,
        mode=mode,
        waypoints=user_waypoints,
    )
    sources = [route.get("source", "unknown") for route in routes]
    print(
        "explorer_loop_routes: "
        f"categories={poi_categories} "
        f"user_waypoints={0 if not user_waypoints else len(user_waypoints)} "
        f"sources={sources}"
    )
    ranked_routes, route_pois = _build_explorer_route_pois(routes, poi_categories, loop_mode=True)
    print(
        "explorer_loop_routes_ranked: "
        f"routes={len(ranked_routes)} "
        f"poi_count={sum(len(pois) for pois in route_pois)}"
    )
    return ranked_routes, route_pois


async def _generate_explorer_a2b_routes(
    start_lng: float,
    start_lat: float,
    end_lng: float,
    end_lat: float,
    mode: str,
    poi_categories: list[str] | None,
    user_waypoints: list[tuple[float, float]] | None,
) -> tuple[list[dict], list[list[POI]]]:
    routes = await route_generator.generate_a2b(
        start_lng,
        start_lat,
        end_lng,
        end_lat,
        mode=mode,
        waypoints=user_waypoints,
    )
    print(
        "explorer_a2b_routes: "
        f"categories={poi_categories} "
        f"user_waypoints={0 if not user_waypoints else len(user_waypoints)} "
        f"sources={[route.get('source', 'unknown') for route in routes]}"
    )
    ranked_routes, route_pois = _build_explorer_route_pois(routes, poi_categories, loop_mode=False)
    print(
        "explorer_a2b_routes_ranked: "
        f"routes={len(ranked_routes)} "
        f"poi_count={sum(len(pois) for pois in route_pois)}"
    )
    return ranked_routes, route_pois


@router.post("/discover-pois", response_model=list[POI])
async def discover_pois(
    body: POIDiscoveryRequest,
) -> list[POI]:
    try:
        pois = await _build_pois(
            polyline=body.polyline,
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
) -> MultiRouteResponse:
    try:
        # 1. Branching based on Route Type
        route_type = getattr(body, "routeType", "loop")
        mode = getattr(body, "mode", "walk")
        app_mode = getattr(body, "appMode", "fitness")
        route_pois: list[list[POI]] | None = None

        target_distance_km = body.distance_km
        if app_mode == "explorer":
            if not body.poi_categories:
                raise HTTPException(status_code=400, detail="Explorer routes require at least one POI category.")
            if route_type == "loop":
                has_distance = body.distance_km is not None
                has_duration = body.target_duration_minutes is not None
                if has_distance == has_duration:
                    raise HTTPException(
                        status_code=400,
                        detail="Explorer loop routes require exactly one of distance_km or target_duration_minutes.",
                    )
                if has_duration:
                    target_distance_km = _target_distance_for_duration(mode, body.target_duration_minutes)
                else:
                    target_distance_km = body.distance_km
                max_distance = MAX_CYCLE_DISTANCE_KM if mode == "cycle" else MAX_WALK_DISTANCE_KM
                if target_distance_km is None or target_distance_km < MIN_DISTANCE_KM:
                    raise HTTPException(
                        status_code=400,
                        detail=f"distance_km must be at least {MIN_DISTANCE_KM:g} for explorer loop routes.",
                    )
                if target_distance_km > max_distance:
                    raise HTTPException(
                        status_code=400,
                        detail=f"distance_km cannot exceed {max_distance:g} for mode={mode}.",
                    )
            elif body.distance_km is not None or body.target_duration_minutes is not None:
                print(
                    "explorer_a2b_target_ignored: "
                    f"distance_km={body.distance_km} "
                    f"target_duration_minutes={body.target_duration_minutes}"
                )
        elif route_type != "a2b":
            if target_distance_km is None:
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

            if app_mode == "explorer":
                routes, route_pois = await _generate_explorer_a2b_routes(
                    body.start_lng,
                    body.start_lat,
                    end_lng,
                    end_lat,
                    mode=mode,
                    poi_categories=body.poi_categories,
                    user_waypoints=body.waypoints,
                )
            else:
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
            routes, route_pois = await _generate_explorer_loop_routes(
                body.start_lng,
                body.start_lat,
                float(target_distance_km),
                mode=mode,
                poi_categories=body.poi_categories,
                user_waypoints=body.waypoints,
            )
            
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Route generation failed. Try again.",
        ) from exc

    if effort_results is None:
        if app_mode == "explorer":
            effort_results = [(None, "Balanced") for _ in routes]
        else:
            effort_results = await enrich_routes_with_effort(routes, mode=mode)
            effort_results = _apply_relative_effort_labels(routes, effort_results, mode)

    return MultiRouteResponse(
        routes=await _build_route_responses(
            routes,
            effort_results,
            route_pois=route_pois,
            app_mode=app_mode,
        )
    )


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
