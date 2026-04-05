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
        ("Cycling Engine", OSRM_BIKE_URL, "driving"),
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


async def test_llm(client):
    section("5. LLM Service")
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    info(f"LLM_PROVIDER = {provider}")

    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        info(f"URL={base}  model={model}")
        t0 = time.monotonic()
        try:
            r = await client.get(f"{base}/api/tags", timeout=5)
            elapsed = time.monotonic() - t0
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                ok(f"Ollama running ({elapsed:.1f}s) — models: {models or '(none pulled yet)'}")
                if any(model in m for m in models):
                    ok(f"'{model}' is available")
                else:
                    warn(f"'{model}' NOT found — run:  ollama pull {model}")
            else:
                warn(f"Ollama HTTP {r.status_code} ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.monotonic() - t0
            warn(f"Ollama unreachable after {elapsed:.1f}s: {e}")
            warn("Routes will generate but POI narrations will be empty strings")

    elif provider == "groq":
        key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        info(f"model={model}")
        if not key:
            warn("GROQ_API_KEY not set — narrations will be empty")
            return
        ok(f"GROQ_API_KEY set (len={len(key)})")
        t0 = time.monotonic()
        try:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": [{"role":"user","content":"say ok"}], "max_tokens": 5},
                timeout=10,
            )
            elapsed = time.monotonic() - t0
            if r.status_code == 200:
                ok(f"Groq API reachable and key valid ({elapsed:.1f}s)")
            else:
                warn(f"Groq HTTP {r.status_code} ({elapsed:.1f}s): {r.text[:120]}")
        except Exception as e:
            elapsed = time.monotonic() - t0
            warn(f"Cannot reach Groq after {elapsed:.1f}s: {e}")


async def test_generate(client):
    section("6. POST /routes/generate-variants (TESTING CYCLE MODE)")
    info(f"Using client timeout: {CLIENT_TIMEOUT_S:.0f}s  (ROUTE_TIMEOUT_S={ROUTE_TIMEOUT_S:.0f}s from .env)")
    payload = {"start_lng": TEST_LNG, "start_lat": TEST_LAT, "distance_km": TEST_DISTANCE_KM, "mode": "cycle"}
    info(f"Payload: {json.dumps(payload)}")
    t0 = time.monotonic()
    try:
        r = await client.post(f"{BASE_URL}/routes/generate-variants", json=payload,
                              timeout=CLIENT_TIMEOUT_S)
        elapsed = time.monotonic() - t0
        if r.status_code == 200:
            routes = r.json().get("routes", [])
            ok(f"Generated in {elapsed:.1f}s — {len(routes)} variants")
            for i, route in enumerate(routes):
                info(f"  Route {chr(65+i)}: {route.get('distance_km', 0):.2f} km  "
                     f"{route.get('duration_minutes', 0)} min  "
                     f"{len(route.get('polyline', []))} pts  [{route.get('source', '?')}]")
            return True
        fail(f"HTTP {r.status_code} after {elapsed:.1f}s")
        try:
            fail(f"Detail: {r.json().get('detail', r.text[:300])}")
        except Exception:
            fail(r.text[:300])
        return False
    except httpx.TimeoutException:
        elapsed = time.monotonic() - t0
        fail(f"Timed out after {elapsed:.1f}s (client limit={CLIENT_TIMEOUT_S:.0f}s)")
        info(f"ROUTE_TIMEOUT_S in .env is {ROUTE_TIMEOUT_S:.0f}s — server may still be waiting on OSRM/LLM")
        return False
    except Exception as e:
        elapsed = time.monotonic() - t0
        fail(f"Error after {elapsed:.1f}s: {e}")
        return False


async def test_variants(client):
    section("7. POST /routes/generate-variants (TESTING WALK MODE)")
    info(f"Using client timeout: {CLIENT_TIMEOUT_S:.0f}s  (ROUTE_TIMEOUT_S={ROUTE_TIMEOUT_S:.0f}s from .env)")
    payload = {"start_lng": TEST_LNG, "start_lat": TEST_LAT, "distance_km": TEST_DISTANCE_KM, "mode": "walk"}
    t0 = time.monotonic()
    try:
        r = await client.post(f"{BASE_URL}/routes/generate-variants", json=payload,
                              timeout=CLIENT_TIMEOUT_S)
        elapsed = time.monotonic() - t0
        if r.status_code == 200:
            routes = r.json().get("routes", [])
            ok(f"Generated in {elapsed:.1f}s — {len(routes)} variants")
            for i, route in enumerate(routes):
                src = route.get("source", "?")
                info(f"  Route {chr(65+i)}: {route.get('distance_km',0):.2f} km  "
                     f"{route.get('duration_minutes',0)} min  "
                     f"{len(route.get('polyline',[]))} pts  [{src}]")
            return True
        fail(f"HTTP {r.status_code} after {elapsed:.1f}s")
        try:
            fail(r.json().get("detail", r.text[:300]))
        except Exception:
            fail(r.text[:300])
        return False
    except httpx.TimeoutException:
        elapsed = time.monotonic() - t0
        fail(f"Timed out after {elapsed:.1f}s (client limit={CLIENT_TIMEOUT_S:.0f}s)")
        return False
    except Exception as e:
        elapsed = time.monotonic() - t0
        fail(f"Error after {elapsed:.1f}s: {e}")
        return False


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
        await test_llm(client)
        gen_ok  = await test_generate(client)
        var_ok  = await test_variants(client)

    section("Summary")
    if not osrm_ok:
        warn("One or more local OSRM containers are unreachable!")
        warn("Check if your Docker containers are running:  docker ps")
    if gen_ok and var_ok:
        ok("Multi-modal route generation working end-to-end ✓")
    else:
        fail("Route generation failing — review errors above (sections 6 & 7)")
    print()

if __name__ == "__main__":
    asyncio.run(main())