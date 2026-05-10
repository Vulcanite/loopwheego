import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import geocode, places, routes

load_dotenv()


def _parse_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="LoopWheeGo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(routes.router, prefix="/routes", tags=["routes"])
app.include_router(places.router, prefix="/places", tags=["places"])
app.include_router(geocode.router, prefix="/geocode", tags=["geocode"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
