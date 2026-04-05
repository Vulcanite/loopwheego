import json
import os
import re
from typing import Any

import httpx


class LLMService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "ollama")

    async def narrate_pois(
        self, pois: list[dict[str, Any]], route_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not pois:
            return []

        distance_km = route_context.get("distance_km", 0)
        start_location_name = route_context.get(
            "start_location_name", "your starting point"
        )
        pois_summary = [
            {
                "osm_id": p["osm_id"],
                "name": p["name"],
                "category": p["category"],
                "tags": p.get("tags", {}),
            }
            for p in pois
        ]

        system_prompt = (
            "You are a knowledgeable local guide for Singapore. You write engaging, "
            "concise walking tour narrations.\n"
            "Respond ONLY with a valid JSON array. No preamble, no markdown, no explanation."
        )
        user_prompt = f"""The walker is doing a {distance_km}km loop starting from {start_location_name}.

Here are the points of interest along the route:
{json.dumps(pois_summary, indent=2)}

For each POI, return a JSON array with objects containing:
- "osm_id": string (same as input)
- "narration": string (2-3 sentences, engaging, specific to Singapore context, mention what to look for)
- "duration_suggested_minutes": integer (realistic time to spend at this stop)

Return ONLY the JSON array."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        content: str = ""
        try:
            if self.provider.lower() == "groq":
                content = await self._call_groq(messages)
            else:
                content = await self._call_ollama(messages)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return self._merge_empty(pois)

        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```\s*$", "", content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return self._merge_empty(pois)

        if not isinstance(parsed, list):
            return self._merge_empty(pois)

        by_osm: dict[str, dict[str, Any]] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            oid = item.get("osm_id")
            if oid is None:
                continue
            by_osm[str(oid)] = item

        out: list[dict[str, Any]] = []
        for p in pois:
            oid = str(p["osm_id"])
            extra = by_osm.get(oid, {})
            narr = extra.get("narration", "")
            if not isinstance(narr, str):
                narr = ""
            dur = extra.get("duration_suggested_minutes", 5)
            try:
                duration_suggested_minutes = int(dur)
            except (TypeError, ValueError):
                duration_suggested_minutes = 5
            merged = {**p, "narration": narr, "duration_suggested_minutes": duration_suggested_minutes}
            out.append(merged)
        return out

    def _merge_empty(self, pois: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {**p, "narration": "", "duration_suggested_minutes": 5}
            for p in pois
        ]

    async def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        url = f"{base}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return str(data["message"]["content"])

    async def _call_groq(self, messages: list[dict[str, str]]) -> str:
        key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        return str(data["choices"][0]["message"]["content"])
