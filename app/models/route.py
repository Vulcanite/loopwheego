from pydantic import BaseModel, ConfigDict
from typing import List, Literal, Optional, Tuple
from app.models.poi import POI

AppMode = Literal["explorer", "fitness"]


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_lng: float
    start_lat: float
    distance_km: Optional[float] = None
    target_duration_minutes: Optional[int] = None
    appMode: AppMode = "fitness"
    mode: str = "walk"
    routeType: Optional[str] = "loop"
    end_lng: Optional[float] = None
    end_lat: Optional[float] = None
    waypoints: Optional[List[Tuple[float, float]]] = None


class RouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: List[Tuple[float, float]]
    distance_km: float
    duration_minutes: int
    pois: List[POI]
    source: str = "unknown"


class MultiRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: List[RouteResponse]


class GPXRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: List[Tuple[float, float]]
    pois: List[POI]
    route_name: str = "LoopWheeGo Route"


class POIDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: List[Tuple[float, float]]
    start_lng: float
    start_lat: float
    distance_km: float
