from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from app.utils.geo import point_to_segment_km

_DURATION_BY_CATEGORY: dict[str, int] = {
    "parks": 20,
    "waterfront": 15,
    "monuments": 15,
    "heritage": 20,
    "museums": 25,
    "viewpoints": 10,
    "hawker_centres": 30,
    "cafes": 20,
    "arts": 20,
    "nature": 20,
}

_CATEGORY_WEIGHTS: dict[str, float] = {
    "monuments": 2.4,
    "heritage": 2.3,
    "waterfront": 2.2,
    "hawker_centres": 2.1,
    "museums": 1.9,
    "viewpoints": 1.8,
    "nature": 1.7,
    "parks": 1.2,
    "cafes": 0.8,
    "arts": 0.7,
}


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


@functools.lru_cache(maxsize=None)
def load_cached_places() -> list[dict[str, Any]]:
    cached_path = _data_dir() / "singapore_places_cached.json"
    fallback_path = _data_dir() / "singapore_places.json"
    source_path = cached_path if cached_path.exists() else fallback_path

    with open(source_path, encoding="utf-8") as f:
        data = json.load(f)

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
                    "category": str(item.get("category", "parks")),
                    "description": str(item.get("description", "")).strip(),
                    "_prominence": int(item.get("_prominence", 6)),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def distance_to_polyline_km(
    place: dict[str, Any],
    polyline: list[list[float]] | list[tuple[float, float]],
) -> float:
    if not polyline or len(polyline) < 2:
        return float("inf")

    return min(
        point_to_segment_km(
            float(place["lat"]),
            float(place["lng"]),
            float(polyline[idx][1]),
            float(polyline[idx][0]),
            float(polyline[idx + 1][1]),
            float(polyline[idx + 1][0]),
        )
        for idx in range(len(polyline) - 1)
    )
