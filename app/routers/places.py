import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/suggested")
async def get_suggested_places() -> list[dict[str, Any]]:
    base = Path(__file__).resolve().parent.parent
    path = base / "data" / "singapore_places.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
