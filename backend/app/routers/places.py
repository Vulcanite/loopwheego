from typing import Any

from fastapi import APIRouter

from app.services import cached_places

router = APIRouter()


@router.get("/suggested")
async def get_suggested_places() -> list[dict[str, Any]]:
    return cached_places.load_cached_places()
