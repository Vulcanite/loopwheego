from pydantic import BaseModel, ConfigDict
from typing import List, Literal, Optional, Tuple
from app.models.poi import POI

AppMode = Literal["explorer", "fitness"]
TransportMode = Literal["walk", "cycle"]
RouteType = Literal["loop", "a2b"]


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_lng: float
    start_lat: float
    distance_km: Optional[float] = None
    target_duration_minutes: Optional[int] = None
    appMode: AppMode = "fitness"
    mode: TransportMode = "walk"
    routeType: RouteType = "loop"
    end_lng: Optional[float] = None
    end_lat: Optional[float] = None
    waypoints: Optional[List[Tuple[float, float]]] = None
    poi_categories: Optional[List[str]] = None


class RouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: List[Tuple[float, float]]
    distance_km: float
    duration_minutes: int
    pois: List[POI]
    source: str = "unknown"
    elevation_gain_m: Optional[float] = None  # None if elevation API unavailable
    effort_label: Optional[str] = None        # "Easier" / "Balanced" / "Tougher"
    label: Optional[str] = None               # display alias = effort_label (frontend contract)


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
