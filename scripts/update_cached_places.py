#!/usr/bin/env python3
"""
Rebuild the curated Singapore Explorer place cache from Overpass.

Usage:
  python3 scripts/update_cached_places.py
  python3 scripts/update_cached_places.py --output app/data/singapore_places_cached.json

The script queries a fixed Singapore bounding box, normalizes raw OSM tags into
stable Explorer-facing categories, assigns a lightweight prominence score, and
writes a deterministic JSON file.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "app" / "data" / "singapore_places_cached.json"
REQUEST_TIMEOUT_S = float(os.getenv("PLACES_CACHE_TIMEOUT_S", "60"))
OVERPASS_RETRIES = int(os.getenv("PLACES_CACHE_RETRIES", "3"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("places_cache")
OVERPASS_ENDPOINTS = tuple(
    endpoint.strip()
    for endpoint in (
        os.getenv("OVERPASS_URL", ""),
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
    )
    if endpoint.strip()
)

# south, west, north, east
SINGAPORE_BBOX = (1.13, 103.60, 1.48, 104.05)


@dataclass(frozen=True)
class CategorySpec:
    name: str
    clauses: tuple[str, ...]
    limit: int


CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        "parks",
        (
            'nwr["leisure"="park"]({bbox});',
            'nwr["leisure"="garden"]({bbox});',
            'nwr["boundary"="national_park"]({bbox});',
            'nwr["leisure"="recreation_ground"]({bbox});',
            'nwr["leisure"="dog_park"]["name"]({bbox});',
            'nwr["leisure"="playground"]["name"]({bbox});',
            'nwr["landuse"="grass"]["name"]({bbox});',
            'nwr["leisure"="park"]["name"]["access"!="private"]({bbox});',
        ),
        120,
    ),
    CategorySpec(
        "nature",
        (
            'nwr["leisure"="nature_reserve"]({bbox});',
            'nwr["boundary"="protected_area"]({bbox});',
            'nwr["natural"="wood"]["name"]({bbox});',
            'nwr["landuse"="forest"]["name"]({bbox});',
            'nwr["natural"="wetland"]["name"]({bbox});',
            'nwr["natural"="heath"]["name"]({bbox});',
            'nwr["natural"="scrub"]["name"]({bbox});',
        ),
        70,
    ),
    CategorySpec(
        "waterfront",
        (
            'nwr["natural"="beach"]({bbox});',
            'nwr["man_made"="pier"]({bbox});',
            'nwr["man_made"="lighthouse"]({bbox});',
            'nwr["amenity"="ferry_terminal"]({bbox});',
            'nwr["leisure"="marina"]({bbox});',
            'nwr["natural"="water"]["name"]({bbox});',
            'nwr["waterway"="reservoir"]["name"]({bbox});',
            'nwr["waterway"="river"]["name"]({bbox});',
            'nwr["natural"="bay"]["name"]({bbox});',
            'nwr["natural"="strait"]["name"]({bbox});',
            'nwr["leisure"="slipway"]["name"]({bbox});',
            'nwr["man_made"="breakwater"]["name"]({bbox});',
        ),
        100,
    ),
    CategorySpec(
        "monuments",
        (
            'nwr["historic"~"monument|memorial|castle|fort|archaeological_site|building|ruins"]({bbox});',
            'nwr["tourism"="attraction"]({bbox});',
            'nwr["historic"="yes"]["name"]({bbox});',
            'nwr["tourism"="artwork"]["name"]({bbox});',
            'nwr["man_made"="tower"]["name"]({bbox});',
            'nwr["historic"="milestone"]["name"]({bbox});',
        ),
        110,
    ),
    CategorySpec(
        "heritage",
        (
            'nwr["historic"="district"]({bbox});',
            'nwr["historic"="conservation_area"]({bbox});',
            'nwr["heritage"]["name"]({bbox});',
            'nwr["building"="shophouse"]["name"]({bbox});',
            'nwr["conservation"="yes"]["name"]({bbox});',
            'nwr["historic"="building"]["name"]({bbox});',
            'nwr["historic"="house"]["name"]({bbox});',
            'nwr["architect"]["name"]({bbox});',
        ),
        85,
    ),
    CategorySpec(
        "museums",
        (
            'nwr["tourism"="museum"]({bbox});',
            'nwr["building"="museum"]({bbox});',
            'nwr["tourism"="gallery"]({bbox});',
            'nwr["museum"]["name"]({bbox});',
        ),
        70,
    ),
    CategorySpec(
        "arts",
        (
            'nwr["amenity"="theatre"]({bbox});',
            'nwr["amenity"="arts_centre"]({bbox});',
            'nwr["amenity"="cinema"]({bbox});',
            'nwr["building"="theatre"]({bbox});',
            'nwr["amenity"="concert_hall"]["name"]({bbox});',
            'nwr["amenity"="community_centre"]["name"]({bbox});',
            'nwr["leisure"="dance"]["name"]({bbox});',
        ),
        70,
    ),
    CategorySpec(
        "viewpoints",
        (
            'nwr["tourism"="viewpoint"]({bbox});',
            'nwr["man_made"="observation_tower"]["name"]({bbox});',
            'nwr["man_made"="tower"]["name"]["tower:type"~"observation|lookout"]({bbox});',
            'nwr["natural"="peak"]["name"]({bbox});',
            'nwr["natural"="hill"]["name"]({bbox});',
        ),
        60,
    ),
    CategorySpec(
        "hawker_centres",
        (
            'nwr["amenity"="hawker_centre"]({bbox});',
            'nwr["amenity"="food_court"]["name"]({bbox});',
            'nwr["building"="hawker_centre"]({bbox});',
            'nwr["amenity"="hawker_centre"]["name"]({bbox});',
            'nwr["shop"="food_court"]["name"]({bbox});',
            'nwr["operator"~"NEA|HDB"]["amenity"]["name"]({bbox});',
        ),
        120,
    ),
    CategorySpec(
        "cafes",
        (
            'nwr["amenity"="cafe"]["name"]({bbox});',
            'nwr["amenity"="restaurant"]["cuisine"="coffee_shop"]["name"]({bbox});',
            'nwr["amenity"="cafe"]["outdoor_seating"="yes"]["name"]({bbox});',
        ),
        90,
    ),
)


def _bbox_text() -> str:
    south, west, north, east = SINGAPORE_BBOX
    return f"{south},{west},{north},{east}"


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "place"


def _element_lat_lng(el: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _prominence(tags: dict[str, str], category: str) -> int:
    score = 5

    if tags.get("wikipedia"):
        score += 3
    if tags.get("wikidata"):
        score += 2
    if tags.get("heritage"):
        score += 2
    if tags.get("website") or tags.get("url"):
        score += 1
    if tags.get("operator"):
        score += 1
    if tags.get("brand"):
        score += 1
    if tags.get("tourism") in {"museum", "attraction", "viewpoint"}:
        score += 2
    if tags.get("historic") in {"monument", "memorial", "fort"}:
        score += 2
    if tags.get("place") in {"suburb", "quarter"}:
        score += 2
    if tags.get("capital") == "yes":
        score += 1

    if category in {"parks", "waterfront", "monuments", "nature", "heritage", "hawker_centres"}:
        score += 1

    return max(1, min(12, score))


def _description(tags: dict[str, str], category: str) -> str:
    parts: list[str] = []

    if tags.get("description"):
        parts.append(tags["description"])
    if tags.get("short_description"):
        parts.append(tags["short_description"])

    if not parts:
        pieces = []
        if category == "parks":
            pieces.append("Park or green space")
        elif category == "nature":
            pieces.append("Nature reserve or forest")
        elif category == "waterfront":
            pieces.append("Waterfront stop")
        elif category == "neighbourhoods":
            pieces.append("Neighbourhood district")
        elif category == "monuments":
            pieces.append("Landmark or heritage site")
        elif category == "heritage":
            pieces.append("Heritage or conservation site")
        elif category == "museums":
            pieces.append("Museum or cultural venue")
        elif category == "arts":
            pieces.append("Arts or performance venue")
        elif category == "viewpoints":
            pieces.append("Viewpoint or scenic overlook")
        elif category == "hawker_centres":
            pieces.append("Hawker centre or food court")
        elif category == "cafes":
            pieces.append("Cafe stop")
        elif category == "markets":
            pieces.append("Market or shopping hub")
        elif category == "religious":
            pieces.append("Place of worship")
        elif category == "sports":
            pieces.append("Sports or recreation facility")
        elif category == "education":
            pieces.append("Educational institution or library")

        if tags.get("tourism"):
            pieces.append(f"tourism:{tags['tourism']}")
        elif tags.get("historic"):
            pieces.append(f"historic:{tags['historic']}")
        elif tags.get("amenity"):
            pieces.append(f"amenity:{tags['amenity']}")
        elif tags.get("place"):
            pieces.append(f"place:{tags['place']}")

        parts.append(", ".join(pieces))

    description = " ".join(part.strip() for part in parts if part.strip())
    return description[:180]


def _build_query(spec: CategorySpec) -> str:
    body = "\n".join(clause.format(bbox=_bbox_text()) for clause in spec.clauses)
    return f"""[out:json][timeout:50];
(
{body}
);
out center tags;
"""


def _build_single_clause_query(clause: str) -> str:
    return f"""[out:json][timeout:35];
(
{clause.format(bbox=_bbox_text())}
);
out center tags;
"""


async def _post_overpass(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    last_error: Exception | None = None

    for endpoint in OVERPASS_ENDPOINTS:
        host = endpoint.split("/")[2]
        for attempt in range(1, OVERPASS_RETRIES + 1):
            try:
                t0 = time.monotonic()
                response = await client.post(
                    endpoint,
                    content=query,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                response.raise_for_status()
                elapsed = time.monotonic() - t0
                log.debug("  Overpass %s -> HTTP %d (%.1fs)", host, response.status_code, elapsed)
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                # 5xx = server-side problem; skip endpoint immediately, no retry
                log.warning("  Overpass %s HTTP %d -> skip endpoint", host, exc.response.status_code)
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                log.warning("  Overpass %s attempt %d/%d timed out/connect error, retrying", host, attempt, OVERPASS_RETRIES)
                if attempt < OVERPASS_RETRIES:
                    await asyncio.sleep(1.0)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                log.warning("  Overpass %s attempt %d/%d failed: %s", host, attempt, OVERPASS_RETRIES, exc)
                if attempt < OVERPASS_RETRIES:
                    await asyncio.sleep(1.0)

    if last_error is None:
        raise RuntimeError("No Overpass endpoints configured.")
    raise last_error


async def _fetch_category(client: httpx.AsyncClient, spec: CategorySpec) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    cat_t0 = time.monotonic()
    raw_total = 0

    log.info("[%s] fetching %d clauses (limit=%d)", spec.name, len(spec.clauses), spec.limit)

    for i, clause in enumerate(spec.clauses, 1):
        clause_t0 = time.monotonic()
        try:
            payload = await _post_overpass(client, _build_single_clause_query(clause))
        except Exception as exc:
            log.error("  [%s] clause %d/%d failed, skipping: %s", spec.name, i, len(spec.clauses), exc)
            continue

        elements = payload.get("elements", [])
        raw_total += len(elements)
        added_this_clause = 0

        for el in elements:
            tags = el.get("tags") or {}
            name = str(tags.get("name", "")).strip()
            if not name:
                continue

            lat_lng = _element_lat_lng(el)
            if lat_lng is None:
                continue
            lat, lng = lat_lng

            dedupe_key = _slugify(name)
            if dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)
            added_this_clause += 1

            out.append(
                {
                    "id": dedupe_key,
                    "name": name,
                    "lat": round(lat, 6),
                    "lng": round(lng, 6),
                    "category": spec.name,
                    "description": _description({k: str(v) for k, v in tags.items()}, spec.name),
                    "_prominence": _prominence({k: str(v) for k, v in tags.items()}, spec.name),
                }
            )

        log.debug(
            "  [%s] clause %d/%d: %d raw elements -> +%d unique (%.1fs)",
            spec.name, i, len(spec.clauses), len(elements), added_this_clause, time.monotonic() - clause_t0,
        )

    out.sort(key=lambda item: (-int(item["_prominence"]), item["name"]))
    result = out[: spec.limit]
    log.info(
        "[%s] done: %d raw -> %d unique -> %d after limit  (%.1fs)",
        spec.name, raw_total, len(out), len(result), time.monotonic() - cat_t0,
    )
    return result


def _dedupe_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for place in places:
        existing = by_id.get(place["id"])
        if existing is None or int(place["_prominence"]) > int(existing["_prominence"]):
            by_id[place["id"]] = place

    out = list(by_id.values())
    out.sort(key=lambda item: (item["category"], -int(item["_prominence"]), item["name"]))
    return out


async def _build_cache() -> list[dict[str, Any]]:
    total_t0 = time.monotonic()
    log.info("=== Singapore place cache rebuild start ===")
    log.info("Categories: %d | Timeout: %.0fs | Retries: %d", len(CATEGORY_SPECS), REQUEST_TIMEOUT_S, OVERPASS_RETRIES)
    log.info("Endpoints: %s", ", ".join(e.split("/")[2] for e in OVERPASS_ENDPOINTS))

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        places: list[dict[str, Any]] = []
        for idx, spec in enumerate(CATEGORY_SPECS, 1):
            log.info("--- [%d/%d] %s ---", idx, len(CATEGORY_SPECS), spec.name)
            fetched = await _fetch_category(client, spec)
            places.extend(fetched)

    log.info("--- deduplication ---")
    before = len(places)
    deduped = _dedupe_places(places)
    log.info("Pre-dedupe: %d  Post-dedupe: %d  (removed %d cross-category dupes)", before, len(deduped), before - len(deduped))

    by_cat: dict[str, int] = {}
    for p in deduped:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    log.info("Category breakdown:")
    for cat, count in sorted(by_cat.items()):
        log.info("  %-20s %d", cat, count)

    log.info("=== Total: %d places in %.1fs ===", len(deduped), time.monotonic() - total_t0)
    return deduped


def _write_output(path: Path, places: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=True, indent=2)
        f.write("\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh cached Singapore Explorer places.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSON path",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    output_path = Path(args.output).resolve()
    places = await _build_cache()
    _write_output(output_path, places)
    log.info("wrote %d places -> %s", len(places), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
