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
from app.services.llm import LLMService
from app.services import route_generator

router = APIRouter()

_llm_singleton = LLMService()

ENABLE_POIS = os.getenv("ENABLE_POIS", "false").lower() == "true"
ENABLE_LLM_NARRATION = os.getenv("ENABLE_LLM_NARRATION", "false").lower() == "true"


def get_llm_service() -> LLMService:
    return _llm_singleton


async def _reverse_geocode_name(lng: float, lat: float) -> str:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                },
                headers={"User-Agent": "LoopWheeGo/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            name = data.get("display_name")
            if isinstance(name, str) and name.strip():
                return name.strip()[:240]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass
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

        if route_type == "a2b":
            # For A to B, we need end coordinates
            end_lng = getattr(body, "end_lng", None)
            end_lat = getattr(body, "end_lat", None)
            if end_lng is None or end_lat is None:
                raise HTTPException(status_code=400, detail="A to B requires an end point.")
            
            routes = await route_generator.generate_a2b(
                body.start_lng, body.start_lat, end_lng, end_lat, mode=mode, waypoints=body.waypoints
            )
        else:
            # Default to Loop generation
            routes = await route_generator.generate_loop_variants(
                body.start_lng, body.start_lat, body.distance_km, count=3, mode=mode, waypoints=body.waypoints
            )
            
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Route generation failed. Try again.",
        ) from exc

    out: list[RouteResponse] = []

    for route in routes:
        polyline = route["polyline"]
        distance_km = float(route["distance_km"])
        duration_minutes = int(route["duration_minutes"])
        source = str(route.get("source", "unknown"))

        # FAST MODE: Return immediately without hitting Overpass/LLM
        pl_tuples = [(float(pt[0]), float(pt[1])) for pt in polyline]
        out.append(
            RouteResponse(
                polyline=pl_tuples,
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                pois=[], # Start completely empty
                source=source,
            )
        )

    return MultiRouteResponse(routes=out)


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