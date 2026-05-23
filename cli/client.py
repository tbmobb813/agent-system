"""
Backend API client for the CLI.

Reads BACKEND_API_URL and BACKEND_API_KEY from environment (or .env).
All functions are async and safe to call from Textual workers.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx
from dotenv import load_dotenv

load_dotenv()
# Also try the backend .env for key sharing in local dev
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

BASE_URL = (os.getenv("BACKEND_API_URL") or "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("BACKEND_API_KEY") or os.getenv("CLI_API_KEY", "")

_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# ── Streaming ─────────────────────────────────────────────────────────────────


async def stream_agent(
    query: str,
    conversation_id: str | None = None,
) -> AsyncIterator[dict]:
    """
    POST /agent/stream — yields parsed event dicts as they arrive.

    Each dict has at minimum a "type" key matching EventType values:
      status, tool_call, tool_result, text_delta, thinking, error, done
    The first status event includes "task_id" which callers can use to stop the run.
    """
    payload: dict = {"query": query, "max_iterations": 10}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/agent/stream",
            headers=_HEADERS,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if raw_line.startswith("data: "):
                    try:
                        yield json.loads(raw_line[6:])
                    except json.JSONDecodeError:
                        pass


# ── Control ───────────────────────────────────────────────────────────────────


async def stop_task(task_id: str) -> bool:
    """POST /agent/stop?task_id=... — returns True if accepted."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{BASE_URL}/agent/stop",
                headers=_HEADERS,
                params={"task_id": task_id},
            )
            return resp.status_code == 200
    except Exception:
        return False


# ── History ───────────────────────────────────────────────────────────────────


async def get_history(limit: int = 15) -> list[dict]:
    """GET /history — returns list of recent task/thread entries."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BASE_URL}/history",
                headers=_HEADERS,
                params={"limit": limit},
            )
            if resp.status_code == 200:
                data = resp.json()
                # endpoint returns {"tasks": [...]} or a bare list
                if isinstance(data, dict):
                    return data.get("tasks", data.get("entries", []))
                return data
    except Exception:
        pass
    return []


# ── Memory ────────────────────────────────────────────────────────────────────


async def search_memories(query: str, limit: int = 6) -> list[dict]:
    """GET /memory/search?q=... — semantic/FTS memory search."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BASE_URL}/memory/search",
                headers=_HEADERS,
                params={"q": query, "limit": limit},
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
    except Exception:
        pass
    return []


# ── Skills ────────────────────────────────────────────────────────────────────


async def get_skills() -> tuple[list[dict], list[str]]:
    """GET /analytics/skills — returns (skills, growth_areas)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BASE_URL}/analytics/skills", headers=_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("skills", []), data.get("growth_areas", [])
    except Exception:
        pass
    return [], []


# ── Budget ────────────────────────────────────────────────────────────────────


async def get_cost_status() -> dict:
    """GET /status/costs — budget and spend summary."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BASE_URL}/status/costs", headers=_HEADERS)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


# ── Config helpers ────────────────────────────────────────────────────────────


def config_errors() -> list[str]:
    """Return list of configuration warnings shown at startup."""
    errors: list[str] = []
    if not API_KEY:
        errors.append(
            "BACKEND_API_KEY not set — requests will be rejected by the backend"
        )
    return errors
