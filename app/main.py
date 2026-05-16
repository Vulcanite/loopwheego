import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import geocode, places, routes
from app.security import require_proxy_auth, validate_security_config

load_dotenv()
validate_security_config()


def _parse_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="LoopWheeGo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-LoopWheeGo-Proxy-Token"],
)

protected_dependencies = [Depends(require_proxy_auth)]

app.include_router(routes.router, prefix="/routes", tags=["routes"], dependencies=protected_dependencies)
app.include_router(places.router, prefix="/places", tags=["places"], dependencies=protected_dependencies)
app.include_router(geocode.router, prefix="/geocode", tags=["geocode"], dependencies=protected_dependencies)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
