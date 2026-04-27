#!/usr/bin/env python3
"""
LoopWheeGo Route Generation Test Script
Run from your project root: python test_routes.py
Make sure your FastAPI server is running first:
  uvicorn app.main:app --reload
"""

import asyncio
import json
import math
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8000"

# Read from .env — defaulting to the local Docker containers
OSRM_FOOT_URL = os.getenv("OSRM_FOOT_URL", "http://localhost:5000")
OSRM_BIKE_URL = os.getenv("OSRM_BIKE_URL", "http://localhost:5001")

ROUTE_TIMEOUT_S = float(os.getenv("ROUTE_TIMEOUT_S", "45"))
CLIENT_TIMEOUT_S = ROUTE_TIMEOUT_S + 15

TEST_LAT = 1.3138
TEST_LNG = 103.8159
TEST_DISTANCE_KM = 5.0
TEST_EXPLORER_DURATION_MIN = 90
TEST_EXPLORER_CATEGORIES = ["monuments", "heritage", "museums"]

BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg): print(f"  {CYAN}→{RESET} {msg}")
def section(t):
    print(f"\n{BOLD}{'─'*50}{RESET}")
    print(f"{BOLD}{t}{RESET}")
    print(f"{BOLD}{'─'*50}{RESET}")


async def test_health(client):
    section("1. FastAPI Health Check")
    try:
        r = await client.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            ok(f"Server is up — {r.json()}")
            return True
        fail(f"HTTP {r.status_code}: {r.text}")
        return False
    except httpx.ConnectError:
        fail(f"Cannot connect to {BASE_URL}")
        fail("Start the server:  uvicorn app.main:app --reload")
        return False
    except Exception as e:
        fail(f"{e}"); return False


async def test_osrm_engines(client):
    section("2. Local OSRM Engines (Foot & Bike)")
    radius_m = (TEST_DISTANCE_KM / (2 * math.pi)) * 1000
    m_per_deg = 111_320.0
    wps = []
    for i in range(4):
        theta = (2 * math.pi * i) / 4
        wps.append((TEST_LNG + radius_m * math.sin(theta) / m_per_deg,
                     TEST_LAT + radius_m * math.cos(theta) / m_per_deg))

    start = f"{TEST_LNG},{TEST_LAT}"
    mid   = ";".join(f"{lng},{lat}" for lng, lat in wps)
    coords = f"{start};{mid};{start}"

    engines = [
        ("Walking Engine", OSRM_FOOT_URL, "foot"),
        ("Cycling Engine", OSRM_BIKE_URL, "bicycle"),
    ]

    all_ok = True
    for name, base_url, profile in engines:
        url = (f"{base_url}/trip/v1/{profile}/{coords}"
               "?roundtrip=true&source=first&destination=last"
               "&geometries=geojson&overview=full&steps=false")
        
        t0 = time.monotonic()
        try:
            r = await client.get(url, timeout=10)
            elapsed = time.monotonic() - t0
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == "Ok" and data.get("trips"):
                    trip = data["trips"][0]
                    ok(f"{name} reachable on {base_url} ({elapsed:.1f}s)")
                    ok(f"  └ Trip Calc: {trip['distance']/1000:.2f} km, "
                       f"{trip['duration']/60:.0f} min, "
                       f"{len(trip['geometry']['coordinates'])} points")
                else:
                    warn(f"{name} code={data.get('code')} — {data.get('message','')}")
                    all_ok = False
            else:
                warn(f"{name} HTTP {r.status_code} ({elapsed:.1f}s)")
                all_ok = False
        except Exception as e:
            elapsed = time.monotonic() - t0
            warn(f"{name} unreachable at {base_url} after {elapsed:.1f}s: {e}")
            warn(f"  └ Make sure the Docker container is running!")
            all_ok = False
            
    return all_ok


async def test_overpass(client):
    section("3. Overpass API (POIs)")
    query = (f"[out:json][timeout:10];\n"
             f"(node[\"tourism\"](around:300,{TEST_LAT},{TEST_LNG});"
             f"node[\"historic\"](around:300,{TEST_LAT},{TEST_LNG}););\nout body;")
    t0 = time.monotonic()
    try:
        r = await client.post("https://lz4.overpass-api.de/api/interpreter",
                              content=query,
                              headers={"Content-Type": "text/plain; charset=utf-8"},
                              timeout=20)
        elapsed = time.monotonic() - t0
        if r.status_code == 200:
            named = [e for e in r.json().get("elements", []) if e.get("tags", {}).get("name")]
            ok(f"Overpass reachable ({elapsed:.1f}s) — {len(named)} named POIs near test point")
            for e in named[:3]:
                info(f"  {e['tags'].get('name')} [{e['tags'].get('tourism') or e['tags'].get('historic')}]")
            return True
        warn(f"Overpass HTTP {r.status_code} ({elapsed:.1f}s)")
        return False
    except Exception as e:
        elapsed = time.monotonic() - t0
        warn(f"Overpass unreachable after {elapsed:.1f}s: {e}")
        return False


async def test_places(client):
    section("4. GET /places/suggested")
    try:
        r = await client.get(f"{BASE_URL}/places/suggested", timeout=5)
        if r.status_code == 200:
            places = r.json()
            ok(f"Returned {len(places)} places")
            for p in places[:3]:
                info(f"  {p['name']} ({p['category']})")
            return True
        fail(f"HTTP {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        fail(f"{e}"); return False


async def test_generate(client):
    section("5. POST /routes/generate-variants (SCENARIO MATRIX)")
    info(f"Using client timeout: {CLIENT_TIMEOUT_S:.0f}s  (ROUTE_TIMEOUT_S={ROUTE_TIMEOUT_S:.0f}s from .env)")
    scenarios = [
        (
            "Fitness Cycle Loop",
            {
                "start_lng": TEST_LNG,
                "start_lat": TEST_LAT,
                "distance_km": TEST_DISTANCE_KM,
                "mode": "cycle",
                "appMode": "fitness",
                "routeType": "loop",
            },
        ),
        (
            "Fitness Walk Loop",
            {
                "start_lng": TEST_LNG,
                "start_lat": TEST_LAT,
                "distance_km": TEST_DISTANCE_KM,
                "mode": "walk",
                "appMode": "fitness",
                "routeType": "loop",
            },
        ),
        (
            "Explorer Cycle Loop",
            {
                "start_lng": TEST_LNG,
                "start_lat": TEST_LAT,
                "target_duration_minutes": TEST_EXPLORER_DURATION_MIN,
                "mode": "cycle",
                "appMode": "explorer",
                "routeType": "loop",
                "poi_categories": TEST_EXPLORER_CATEGORIES,
            },
        ),
        (
            "Explorer Walk Loop",
            {
                "start_lng": TEST_LNG,
                "start_lat": TEST_LAT,
                "target_duration_minutes": TEST_EXPLORER_DURATION_MIN,
                "mode": "walk",
                "appMode": "explorer",
                "routeType": "loop",
                "poi_categories": TEST_EXPLORER_CATEGORIES,
            },
        ),
    ]

    all_ok = True
    for idx, (name, payload) in enumerate(scenarios, start=1):
        info(f"[{idx}/{len(scenarios)}] {name}")
        info(f"Payload: {json.dumps(payload)}")
        t0 = time.monotonic()
        try:
            r = await client.post(
                f"{BASE_URL}/routes/generate-variants",
                json=payload,
                timeout=CLIENT_TIMEOUT_S,
            )
            elapsed = time.monotonic() - t0
            if r.status_code == 200:
                routes = r.json().get("routes", [])
                ok(f"{name}: generated in {elapsed:.1f}s — {len(routes)} variants")
                for route_idx, route in enumerate(routes):
                    label = route.get("label") or route.get("effort_label") or "-"
                    poi_count = len(route.get("pois", []))
                    info(
                        f"  Route {chr(65 + route_idx)}: "
                        f"{route.get('distance_km', 0):.2f} km  "
                        f"{route.get('duration_minutes', 0)} min  "
                        f"{len(route.get('polyline', []))} pts  "
                        f"POIs={poi_count}  "
                        f"label={label}  "
                        f"[{route.get('source', '?')}]"
                    )
            else:
                all_ok = False
                fail(f"{name}: HTTP {r.status_code} after {elapsed:.1f}s")
                try:
                    fail(f"Detail: {r.json().get('detail', r.text[:300])}")
                except Exception:
                    fail(r.text[:300])
        except httpx.TimeoutException:
            all_ok = False
            elapsed = time.monotonic() - t0
            fail(f"{name}: timed out after {elapsed:.1f}s (client limit={CLIENT_TIMEOUT_S:.0f}s)")
        except Exception as e:
            all_ok = False
            elapsed = time.monotonic() - t0
            fail(f"{name}: error after {elapsed:.1f}s: {e}")

    return all_ok


async def main():
    print(f"\n{BOLD}LoopWheeGo API Test Suite{RESET}")
    print(f"Server         : {BASE_URL}")
    print(f"Foot Container : {OSRM_FOOT_URL}")
    print(f"Bike Container : {OSRM_BIKE_URL}")
    print(f"ROUTE_TIMEOUT_S: {ROUTE_TIMEOUT_S:.0f}s  (from .env)")
    print(f"Test point     : Botanic Gardens ({TEST_LAT}, {TEST_LNG}), {TEST_DISTANCE_KM} km loop")

    async with httpx.AsyncClient() as client:
        alive = await test_health(client)
        if not alive:
            print(f"\n{RED}Server not reachable — start it first.{RESET}\n")
            sys.exit(1)

        osrm_ok = await test_osrm_engines(client)
        await test_overpass(client)
        await test_places(client)
        scenarios_ok = await test_generate(client)

    section("Summary")
    if not osrm_ok:
        warn("One or more local OSRM containers are unreachable!")
        warn("Check if your Docker containers are running:  docker ps")
    if scenarios_ok:
        ok("Multi-modal route generation working end-to-end ✓")
    else:
        fail("Route generation failing — review errors above (section 6)")
    print()

if __name__ == "__main__":
    asyncio.run(main())
