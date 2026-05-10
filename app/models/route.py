from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.poi import POI

AppMode = Literal["explorer", "fitness"]
TransportMode = Literal["walk", "cycle"]
RouteType = Literal["loop", "a2b"]
ExplorerCategory = Literal[
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
]

_SG_MIN_LAT, _SG_MAX_LAT = 1.13, 1.48
_SG_MIN_LNG, _SG_MAX_LNG = 103.60, 104.05


def _in_singapore(lat: float, lng: float) -> bool:
    return _SG_MIN_LAT <= lat <= _SG_MAX_LAT and _SG_MIN_LNG <= lng <= _SG_MAX_LNG


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_lng: float
    start_lat: float
    distance_km: float | None = Field(default=None, gt=0, le=100)
    target_duration_minutes: int | None = Field(default=None, ge=15, le=360)
    appMode: AppMode = "fitness"
    mode: TransportMode = "walk"
    routeType: RouteType = "loop"
    end_lng: float | None = None
    end_lat: float | None = None
    waypoints: list[tuple[float, float]] | None = Field(default=None, max_length=5)
    poi_categories: list[ExplorerCategory] | None = Field(default=None, max_length=10)
    max_routes: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="after")
    def validate_singapore_coords(self) -> "RouteRequest":
        if not _in_singapore(self.start_lat, self.start_lng):
            raise ValueError("start coordinates must be within Singapore")
        if self.end_lat is not None and self.end_lng is not None:
            if not _in_singapore(self.end_lat, self.end_lng):
                raise ValueError("end coordinates must be within Singapore")
        if self.waypoints:
            for lng, lat in self.waypoints:
                if not _in_singapore(lat, lng):
                    raise ValueError("all waypoints must be within Singapore")
        return self


class RouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: list[tuple[float, float]]
    distance_km: float
    duration_minutes: int
    pois: list[POI]
    source: str = "unknown"
    elevation_gain_m: float | None = None
    effort_label: str | None = None
    label: str | None = None


class MultiRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routes: list[RouteResponse]


class GPXRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: list[tuple[float, float]] = Field(min_length=2, max_length=10_000)
    pois: list[POI] = Field(max_length=100)
    route_name: str = Field(default="LoopWheeGo Route", max_length=80)


class POIDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polyline: list[tuple[float, float]] = Field(min_length=2, max_length=10_000)
