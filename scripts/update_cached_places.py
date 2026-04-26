#!/usr/bin/env python3
"""
Maintain the curated Singapore Explorer place cache from Overpass.

This script no longer treats cache generation as a single fragile one-shot task.
It supports a simple maintenance pipeline:

  python3 scripts/update_cached_places.py
  python3 scripts/update_cached_places.py refresh
  python3 scripts/update_cached_places.py fetch
  python3 scripts/update_cached_places.py build
  python3 scripts/update_cached_places.py validate

Pipeline:
1. `fetch`    -> queries Overpass and stores per-category raw snapshots on disk
2. `build`    -> reads local snapshots, normalizes, dedupes, scores, and writes cache JSON
3. `validate` -> checks the generated cache before promotion
4. `refresh`  -> fetch + build + validate, only replacing the cache when validation passes

Runtime app requests still depend only on `app/data/singapore_places_cached.json`.
Overpass is used only during cache maintenance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "app" / "data"
RAW_DIR = DATA_DIR / "raw_places"
DEFAULT_OUTPUT = DATA_DIR / "singapore_places_cached.json"
DEFAULT_FALLBACK = DATA_DIR / "singapore_places.json"

REQUEST_TIMEOUT_S = float(os.getenv("PLACES_CACHE_TIMEOUT_S", "60"))
OVERPASS_RETRIES = int(os.getenv("PLACES_CACHE_RETRIES", "3"))
DEFAULT_DEDUPE_RADIUS_KM = float(os.getenv("PLACES_CACHE_DEDUPE_RADIUS_KM", "0.18"))
DEFAULT_MIN_CATEGORY_COUNT = int(os.getenv("PLACES_CACHE_MIN_CATEGORY_COUNT", "8"))
OVERPASS_HEADERS = {
    "User-Agent": "curl/8.0",
    "Accept": "*/*",
}

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
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
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
        260,
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
        120,
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
        260,
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
        260,
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
        120,
    ),
    CategorySpec(
        "museums",
        (
            'nwr["tourism"="museum"]({bbox});',
            'nwr["building"="museum"]({bbox});',
            'nwr["tourism"="gallery"]({bbox});',
            'nwr["museum"]["name"]({bbox});',
        ),
        120,
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
        180,
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
        120,
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
        260,
    ),
    CategorySpec(
        "cafes",
        (
            'nwr["amenity"="cafe"]["name"]({bbox});',
            'nwr["amenity"="restaurant"]["cuisine"="coffee_shop"]["name"]({bbox});',
            'nwr["amenity"="cafe"]["outdoor_seating"="yes"]["name"]({bbox});',
        ),
        300,
    ),
)

SPEC_BY_NAME = {spec.name: spec for spec in CATEGORY_SPECS}


def _bbox_text() -> str:
    south, west, north, east = SINGAPORE_BBOX
    return f"{south},{west},{north},{east}"


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "place"


def _within_singapore_bounds(lat: float, lng: float) -> bool:
    south, west, north, east = SINGAPORE_BBOX
    return south <= lat <= north and west <= lng <= east


def _stable_place_id(name: str, lat: float, lng: float) -> str:
    return f"{_slugify(name)}-{abs(int(round(lat * 10000))):05d}-{abs(int(round(lng * 10000))):07d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


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


def _build_single_clause_query(clause: str) -> str:
    return f"""[out:json][timeout:35];
(
{clause.format(bbox=_bbox_text())}
);
out body center;
"""


async def _post_overpass(client: httpx.AsyncClient, query: str) -> tuple[dict[str, Any], str]:
    last_error: Exception | None = None

    for endpoint in OVERPASS_ENDPOINTS:
        host = endpoint.split("/")[2]
        for attempt in range(1, OVERPASS_RETRIES + 1):
            try:
                # Different public Overpass deployments can be picky about POST shape.
                # Try the form-encoded interpreter style first, then fall back to raw text.
                request_variants = (
                    {"data": {"data": query}, "headers": OVERPASS_HEADERS},
                    {
                        "content": query,
                        "headers": {
                            **OVERPASS_HEADERS,
                            "Content-Type": "text/plain; charset=utf-8",
                        },
                    },
                )
                for variant in request_variants:
                    response = await client.post(endpoint, **variant)
                    if response.is_success:
                        return response.json(), endpoint
                    if response.status_code in {400, 406}:
                        last_error = httpx.HTTPStatusError(
                            f"{response.status_code} from {endpoint}: {response.text[:200]}",
                            request=response.request,
                            response=response,
                        )
                        continue
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                log.warning(
                    "  Overpass %s HTTP %d -> skip endpoint (%s)",
                    host,
                    exc.response.status_code,
                    exc.response.text[:120].replace("\n", " "),
                )
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                log.warning(
                    "  Overpass %s attempt %d/%d timed out/connect error, retrying",
                    host,
                    attempt,
                    OVERPASS_RETRIES,
                )
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


def _normalize_element(el: dict[str, Any], category: str) -> dict[str, Any] | None:
    tags = el.get("tags") or {}
    name = str(tags.get("name", "")).strip()
    if not name:
        return None

    lat_lng = _element_lat_lng(el)
    if lat_lng is None:
        return None
    lat, lng = lat_lng
    if not _within_singapore_bounds(lat, lng):
        return None

    tag_map = {k: str(v) for k, v in tags.items()}
    return {
        "id": _stable_place_id(name, lat, lng),
        "name": name,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "category": category,
        "description": _description(tag_map, category),
        "_prominence": _prominence(tag_map, category),
        "_tags": tag_map,
    }


def _dedupe_within_category(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for place in places:
        existing = by_id.get(place["id"])
        if existing is None or int(place["_prominence"]) > int(existing["_prominence"]):
            by_id[place["id"]] = place
    return sorted(by_id.values(), key=lambda item: (-int(item["_prominence"]), item["name"]))


async def _fetch_category_snapshot(client: httpx.AsyncClient, spec: CategorySpec) -> dict[str, Any]:
    cat_t0 = time.monotonic()
    log.info("[%s] fetching %d clauses (limit=%d)", spec.name, len(spec.clauses), spec.limit)

    normalized_places: list[dict[str, Any]] = []
    raw_total = 0
    endpoints_used: list[str] = []
    clause_errors: list[dict[str, str]] = []

    for idx, clause in enumerate(spec.clauses, 1):
        try:
            payload, endpoint = await _post_overpass(client, _build_single_clause_query(clause))
            endpoints_used.append(endpoint)
        except Exception as exc:
            log.error("  [%s] clause %d/%d failed, skipping: %s", spec.name, idx, len(spec.clauses), exc)
            clause_errors.append({"clause_index": str(idx), "error": str(exc)})
            continue

        elements = payload.get("elements", [])
        raw_total += len(elements)
        for el in elements:
            place = _normalize_element(el, spec.name)
            if place is not None:
                normalized_places.append(place)

    deduped = _dedupe_within_category(normalized_places)
    snapshot = {
        "category": spec.name,
        "fetched_at": _now_iso(),
        "bbox": _bbox_text(),
        "limit": spec.limit,
        "clauses": list(spec.clauses),
        "raw_total": raw_total,
        "unique_total": len(deduped),
        "endpoints_used": endpoints_used,
        "clause_errors": clause_errors,
        "places": deduped,
    }
    log.info(
        "[%s] done: %d raw -> %d unique snapshot  (%.1fs)",
        spec.name,
        raw_total,
        len(deduped),
        time.monotonic() - cat_t0,
    )
    return snapshot


def _snapshot_path(raw_dir: Path, category: str) -> Path:
    return raw_dir / f"{category}.json"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2)
        f.write("\n")


def _load_snapshot(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("places"), list):
        raise ValueError(f"Invalid snapshot format: {path}")
    return data


async def _fetch_raw_snapshots(raw_dir: Path, categories: list[str] | None = None) -> tuple[int, int]:
    selected_specs = [
        SPEC_BY_NAME[name] for name in (categories or list(SPEC_BY_NAME.keys()))
        if name in SPEC_BY_NAME
    ]
    succeeded = 0
    failed = 0
    total_t0 = time.monotonic()
    log.info("=== raw fetch start ===")
    log.info("Categories: %d | Raw dir: %s", len(selected_specs), raw_dir)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        for idx, spec in enumerate(selected_specs, 1):
            log.info("--- [%d/%d] %s ---", idx, len(selected_specs), spec.name)
            try:
                snapshot = await _fetch_category_snapshot(client, spec)
                _write_json(_snapshot_path(raw_dir, spec.name), snapshot)
                succeeded += 1
            except Exception as exc:
                log.error("[%s] snapshot fetch failed: %s", spec.name, exc)
                failed += 1

    manifest = {
        "fetched_at": _now_iso(),
        "categories_requested": [spec.name for spec in selected_specs],
        "categories_succeeded": succeeded,
        "categories_failed": failed,
        "raw_dir": str(raw_dir),
        "elapsed_seconds": round(time.monotonic() - total_t0, 1),
    }
    _write_json(raw_dir / "_manifest.json", manifest)
    log.info("=== raw fetch end: %d succeeded, %d failed in %.1fs ===", succeeded, failed, time.monotonic() - total_t0)
    return succeeded, failed


def _snapshot_places(raw_dir: Path, category: str) -> list[dict[str, Any]]:
    path = _snapshot_path(raw_dir, category)
    if not path.exists():
        raise FileNotFoundError(f"Missing raw snapshot for category={category}: {path}")
    return list(_load_snapshot(path).get("places", []))


def _sanitize_snapshot_place(place: dict[str, Any], category: str) -> dict[str, Any] | None:
    try:
        lat = float(place["lat"])
        lng = float(place["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    if not _within_singapore_bounds(lat, lng):
        return None

    name = str(place.get("name", "")).strip()
    if not name:
        return None

    description = str(place.get("description", "")).strip()
    prominence = int(place.get("_prominence", 1))
    return {
        "id": _stable_place_id(name, lat, lng),
        "name": name,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "category": category,
        "description": description[:180],
        "_prominence": max(1, min(12, prominence)),
    }


def _dedupe_places(places: list[dict[str, Any]], radius_km: float) -> list[dict[str, Any]]:
    ordered = sorted(
        places,
        key=lambda item: (
            item["category"],
            -int(item["_prominence"]),
            item["name"],
        ),
    )
    kept: list[dict[str, Any]] = []
    for place in ordered:
        duplicate_idx = next(
            (
                idx
                for idx, existing in enumerate(kept)
                if existing["id"] == place["id"]
                and _haversine_km(
                    float(existing["lat"]),
                    float(existing["lng"]),
                    float(place["lat"]),
                    float(place["lng"]),
                ) <= radius_km
            ),
            None,
        )
        if duplicate_idx is None:
            kept.append(place)
            continue

        existing = kept[duplicate_idx]
        replace = False
        if int(place["_prominence"]) > int(existing["_prominence"]):
            replace = True
        elif int(place["_prominence"]) == int(existing["_prominence"]) and len(place.get("description", "")) > len(existing.get("description", "")):
            replace = True

        if replace:
            kept[duplicate_idx] = place

    kept.sort(key=lambda item: (item["category"], -int(item["_prominence"]), item["name"]))
    return kept


def _build_cache_from_raw(raw_dir: Path, output_path: Path, radius_km: float) -> list[dict[str, Any]]:
    log.info("=== build cache start ===")
    log.info("Raw dir: %s", raw_dir)
    all_places: list[dict[str, Any]] = []
    category_counts_pre_limit: dict[str, int] = {}

    for spec in CATEGORY_SPECS:
        places = [
            sanitized
            for place in _snapshot_places(raw_dir, spec.name)
            if (sanitized := _sanitize_snapshot_place(place, spec.name)) is not None
        ]
        places.sort(key=lambda item: (-int(item["_prominence"]), item["name"]))
        category_counts_pre_limit[spec.name] = len(places)
        trimmed = places[: spec.limit]
        all_places.extend(trimmed)
        log.info(
            "[%s] snapshot=%d -> after limit=%d",
            spec.name,
            len(places),
            len(trimmed),
        )

    deduped = _dedupe_places(all_places, radius_km=radius_km)
    final_places = [
        {
            "id": place["id"],
            "name": place["name"],
            "lat": place["lat"],
            "lng": place["lng"],
            "category": place["category"],
            "description": place["description"],
            "_prominence": place["_prominence"],
        }
        for place in deduped
    ]
    _write_json(output_path, final_places)

    report = {
        "built_at": _now_iso(),
        "raw_dir": str(raw_dir),
        "output_path": str(output_path),
        "dedupe_radius_km": radius_km,
        "category_counts_pre_limit": category_counts_pre_limit,
        "total_after_build": len(final_places),
    }
    _write_json(raw_dir / "_build_report.json", report)

    log.info("=== build cache end: wrote %d places -> %s ===", len(final_places), output_path)
    return final_places


def _validate_places(
    places: list[dict[str, Any]],
    *,
    min_category_count: int,
    strict_categories: bool,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not places:
        errors.append("cache is empty")
        return False, errors

    required_categories = [spec.name for spec in CATEGORY_SPECS]
    category_counts = {category: 0 for category in required_categories}
    ids: set[str] = set()
    unexpected_category_counts: dict[str, int] = {}

    for idx, place in enumerate(places):
        for field in ("id", "name", "lat", "lng", "category", "description", "_prominence"):
            if field not in place:
                errors.append(f"place[{idx}] missing field={field}")
        place_id = str(place.get("id", ""))
        if place_id in ids:
            errors.append(f"duplicate id={place_id}")
        ids.add(place_id)

        category = str(place.get("category", ""))
        if category not in category_counts:
            unexpected_category_counts[category] = unexpected_category_counts.get(category, 0) + 1
        else:
            category_counts[category] += 1

        try:
            lat = float(place["lat"])
            lng = float(place["lng"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid coordinates for id={place_id}")
            continue

        if not _within_singapore_bounds(lat, lng):
            errors.append(f"out-of-bounds place id={place_id} lat={lat} lng={lng}")

    for category, count in category_counts.items():
        if count < min_category_count:
            errors.append(f"category={category} underfilled ({count} < {min_category_count})")

    if unexpected_category_counts:
        joined = ", ".join(
            f"{category} ({count})"
            for category, count in sorted(unexpected_category_counts.items())
        )
        message = f"unexpected categories present: {joined}"
        if strict_categories:
            errors.append(message)
        else:
            log.warning(message)

    return not errors, errors


def _validate_output_file(
    path: Path,
    min_category_count: int,
    *,
    strict_categories: bool,
) -> tuple[bool, list[str]]:
    if not path.exists():
        return False, [f"missing output file: {path}"]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return False, [f"output file is not a list: {path}"]
    return _validate_places(
        data,
        min_category_count=min_category_count,
        strict_categories=strict_categories,
    )


def _atomic_promote(tmp_output: Path, final_output: Path) -> None:
    final_output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp_output, final_output)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh cached Singapore Explorer places.")
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--raw-dir", default=str(RAW_DIR), help="Directory for raw per-category snapshots")
    common.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")

    fetch_parser = sub.add_parser("fetch", parents=[common], help="Fetch and store raw category snapshots")
    fetch_parser.add_argument("--categories", nargs="*", help="Optional subset of categories to fetch")

    build_parser = sub.add_parser("build", parents=[common], help="Build cache JSON from local raw snapshots")
    build_parser.add_argument("--dedupe-radius-km", type=float, default=DEFAULT_DEDUPE_RADIUS_KM)

    validate_parser = sub.add_parser("validate", parents=[common], help="Validate a built cache JSON file")
    validate_parser.add_argument("--min-category-count", type=int, default=DEFAULT_MIN_CATEGORY_COUNT)
    validate_parser.add_argument(
        "--strict-categories",
        action="store_true",
        help="Fail validation when categories outside the current Explorer target set are present",
    )

    refresh_parser = sub.add_parser("refresh", parents=[common], help="Fetch, build, validate, and promote cache")
    refresh_parser.add_argument("--categories", nargs="*", help="Optional subset of categories to fetch")
    refresh_parser.add_argument("--dedupe-radius-km", type=float, default=DEFAULT_DEDUPE_RADIUS_KM)
    refresh_parser.add_argument("--min-category-count", type=int, default=DEFAULT_MIN_CATEGORY_COUNT)
    refresh_parser.add_argument(
        "--strict-categories",
        action="store_true",
        help="Fail refresh if unexpected categories somehow remain in the built output",
    )

    parser.set_defaults(command="refresh")
    return parser.parse_args()


async def _run_fetch(raw_dir: Path, categories: list[str] | None) -> int:
    succeeded, failed = await _fetch_raw_snapshots(raw_dir, categories=categories)
    return 0 if succeeded > 0 or failed == 0 else 1


def _run_build(raw_dir: Path, output_path: Path, dedupe_radius_km: float) -> int:
    _build_cache_from_raw(raw_dir, output_path, radius_km=dedupe_radius_km)
    return 0


def _run_validate(output_path: Path, min_category_count: int, *, strict_categories: bool) -> int:
    ok, errors = _validate_output_file(
        output_path,
        min_category_count=min_category_count,
        strict_categories=strict_categories,
    )
    if ok:
        log.info("validation passed: %s", output_path)
        return 0
    log.error("validation failed: %s", output_path)
    for error in errors:
        log.error("  - %s", error)
    return 1


async def _run_refresh(
    raw_dir: Path,
    output_path: Path,
    categories: list[str] | None,
    dedupe_radius_km: float,
    min_category_count: int,
    strict_categories: bool,
) -> int:
    await _fetch_raw_snapshots(raw_dir, categories=categories)

    tmp_output = output_path.with_suffix(output_path.suffix + ".tmp")
    places = _build_cache_from_raw(raw_dir, tmp_output, radius_km=dedupe_radius_km)
    ok, errors = _validate_places(
        places,
        min_category_count=min_category_count,
        strict_categories=strict_categories,
    )
    if not ok:
        log.error("refresh validation failed; previous cache remains unchanged")
        for error in errors:
            log.error("  - %s", error)
        try:
            tmp_output.unlink(missing_ok=True)
        except OSError:
            pass
        return 1

    _atomic_promote(tmp_output, output_path)
    log.info("refresh promoted new cache -> %s", output_path)
    return 0


async def _main() -> int:
    args = _parse_args()
    raw_dir = Path(args.raw_dir).resolve()
    output_path = Path(args.output).resolve()

    if args.command == "fetch":
        return await _run_fetch(raw_dir, categories=args.categories)
    if args.command == "build":
        return _run_build(raw_dir, output_path, dedupe_radius_km=args.dedupe_radius_km)
    if args.command == "validate":
        return _run_validate(
            output_path,
            min_category_count=args.min_category_count,
            strict_categories=args.strict_categories,
        )
    if args.command == "refresh":
        return await _run_refresh(
            raw_dir,
            output_path,
            categories=args.categories,
            dedupe_radius_km=args.dedupe_radius_km,
            min_category_count=args.min_category_count,
            strict_categories=args.strict_categories,
        )

    log.error("unknown command: %s", args.command)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
