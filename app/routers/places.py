from typing import Any

from fastapi import APIRouter

from app.services import overpass

router = APIRouter()


@router.get("/suggested")
async def get_suggested_places() -> list[dict[str, Any]]:
    return await overpass.fetch_suggested_places()
