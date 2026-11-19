from pydantic import BaseModel, ConfigDict


class POI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    lat: float
    lng: float
    category: str
    narration: str
    duration_suggested_minutes: int
