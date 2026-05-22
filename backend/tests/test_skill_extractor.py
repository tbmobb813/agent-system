"""Tests for app/agent/skill_extractor.py"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.agent.skill_extractor as sx
from app.agent.skill_extractor import (
    _call_extraction_llm,
    _find_similar_skill,
    extract_skills_from_recent_episodes,
    maybe_extract_skill,
)

_EPISODE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_SKILL_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_GOOD_EPISODE = {
    "id": _EPISODE_ID,
    "user_id": "default",
    "query": "analyse sales CSV and produce a summary chart",
    "outcome": "Generated bar chart and saved to output.png",
    "tools_used": ["code_execution", "file_operations"],
    "duration_ms": 12_000,
    "authored_skill_id": None,
}

_SKILL_JSON = {
    "name": "Analyse CSV and generate chart",
    "pattern": "Load a CSV, compute aggregates, and render a chart.",
    "solution": "Use pandas to read the file, groupby to aggregate, matplotlib to plot.",
    "preconditions": ["CSV file is available"],
    "gotchas": ["Check for empty rows before aggregating"],
}


# ── _call_extraction_llm ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_extraction_llm_returns_parsed_dict(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(_SKILL_JSON)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(sx, "_openrouter_client", lambda: mock_client)

    result = await _call_extraction_llm(_GOOD_EPISODE)

    assert result["name"] == _SKILL_JSON["name"]
    assert result["pattern"] == _SKILL_JSON["pattern"]


@pytest.mark.asyncio
async def test_call_extraction_llm_strips_markdown_fences(monkeypatch):
    raw = f"```json\n{json.dumps(_SKILL_JSON)}\n```"
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = raw
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(sx, "_openrouter_client", lambda: mock_client)

    result = await _call_extraction_llm(_GOOD_EPISODE)
    assert result["name"] == _SKILL_JSON["name"]


@pytest.mark.asyncio
async def test_call_extraction_llm_returns_none_on_invalid_json(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "not json"
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(sx, "_openrouter_client", lambda: mock_client)

    result = await _call_extraction_llm(_GOOD_EPISODE)
    assert result is None


@pytest.mark.asyncio
async def test_call_extraction_llm_returns_none_on_api_error(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("timeout"))
    monkeypatch.setattr(sx, "_openrouter_client", lambda: mock_client)

    result = await _call_extraction_llm(_GOOD_EPISODE)
    assert result is None


@pytest.mark.asyncio
async def test_call_extraction_llm_returns_none_for_non_dict_response(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = '["a", "b"]'
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(sx, "_openrouter_client", lambda: mock_client)

    result = await _call_extraction_llm(_GOOD_EPISODE)
    assert result is None


# ── _find_similar_skill ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_similar_skill_returns_none_when_no_pool(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", None)
    result = await _find_similar_skill("default", [0.1] * 1536)
    assert result is None


@pytest.mark.asyncio
async def test_find_similar_skill_returns_none_below_threshold(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(
        return_value=[
            {
                "id": _SKILL_ID,
                "name": "x",
                "use_count": 1,
                "success_count": 1,
                "similarity": 0.70,
            }
        ]
    )
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_async_ctx(mock_conn))
    monkeypatch.setattr(sx._db, "db_pool", mock_pool)

    result = await _find_similar_skill("default", [0.1] * 1536)
    assert result is None


@pytest.mark.asyncio
async def test_find_similar_skill_returns_row_above_threshold(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(
        return_value=[
            {
                "id": _SKILL_ID,
                "name": "x",
                "use_count": 2,
                "success_count": 2,
                "similarity": 0.92,
            }
        ]
    )
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_async_ctx(mock_conn))
    monkeypatch.setattr(sx._db, "db_pool", mock_pool)

    result = await _find_similar_skill("default", [0.1] * 1536)
    assert result is not None
    assert str(result["id"]) == _SKILL_ID


@pytest.mark.asyncio
async def test_find_similar_skill_returns_none_on_db_error(monkeypatch):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=RuntimeError("vector index unavailable"))
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_async_ctx(mock_conn))
    monkeypatch.setattr(sx._db, "db_pool", mock_pool)

    result = await _find_similar_skill("default", [0.1] * 1536)
    assert result is None


# ── maybe_extract_skill ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maybe_extract_skill_returns_none_when_no_pool(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", None)
    result = await maybe_extract_skill(_GOOD_EPISODE)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_extract_skill_skips_already_processed_episode(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    episode = {**_GOOD_EPISODE, "authored_skill_id": _SKILL_ID}
    result = await maybe_extract_skill(episode)
    assert result == _SKILL_ID


@pytest.mark.asyncio
async def test_maybe_extract_skill_returns_none_when_llm_fails(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    monkeypatch.setattr(sx, "_call_extraction_llm", AsyncMock(return_value=None))

    result = await maybe_extract_skill(_GOOD_EPISODE)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_extract_skill_returns_none_when_llm_missing_fields(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    monkeypatch.setattr(
        sx, "_call_extraction_llm", AsyncMock(return_value={"name": "", "pattern": ""})
    )
    result = await maybe_extract_skill(_GOOD_EPISODE)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_extract_skill_creates_new_skill(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", MagicMock())
    monkeypatch.setattr(sx, "_call_extraction_llm", AsyncMock(return_value=_SKILL_JSON))
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=None))  # no embedding
    monkeypatch.setattr(sx, "_find_similar_skill", AsyncMock(return_value=None))
    monkeypatch.setattr(sx._db, "fetchrow", AsyncMock(return_value={"id": _SKILL_ID}))
    execute_calls: list[str] = []

    async def fake_execute(sql, *args):
        execute_calls.append(sql.strip().split()[0].upper())

    monkeypatch.setattr(sx._db, "execute", fake_execute)

    result = await maybe_extract_skill(_GOOD_EPISODE)

    assert result == _SKILL_ID
    # Should UPDATE the episode to link the skill
    assert "UPDATE" in execute_calls


@pytest.mark.asyncio
async def test_maybe_extract_skill_increments_existing_on_dedup(monkeypatch):
    existing = {
        "id": _SKILL_ID,
        "name": "existing skill",
        "use_count": 3,
        "success_count": 3,
        "similarity": 0.91,
    }

    monkeypatch.setattr(sx._db, "db_pool", MagicMock())
    monkeypatch.setattr(sx, "_call_extraction_llm", AsyncMock(return_value=_SKILL_JSON))
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=[0.1] * 1536))
    monkeypatch.setattr(sx, "_find_similar_skill", AsyncMock(return_value=existing))

    execute_calls: list[tuple] = []

    async def fake_execute(sql, *args):
        execute_calls.append((sql, args))

    monkeypatch.setattr(sx._db, "execute", fake_execute)

    result = await maybe_extract_skill(_GOOD_EPISODE)

    assert result == _SKILL_ID
    # First UPDATE increments use_count; second links episode
    sqls = [c[0] for c in execute_calls]
    assert any("use_count" in s for s in sqls)
    assert any("authored_skill_id" in s for s in sqls)


@pytest.mark.asyncio
async def test_maybe_extract_skill_returns_none_on_insert_error(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", MagicMock())
    monkeypatch.setattr(sx, "_call_extraction_llm", AsyncMock(return_value=_SKILL_JSON))
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=None))
    monkeypatch.setattr(sx, "_find_similar_skill", AsyncMock(return_value=None))
    monkeypatch.setattr(
        sx._db, "fetchrow", AsyncMock(side_effect=RuntimeError("insert failed"))
    )

    result = await maybe_extract_skill(_GOOD_EPISODE)
    assert result is None


# ── extract_skills_from_recent_episodes ───────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_skills_returns_zero_when_no_pool(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", None)
    result = await extract_skills_from_recent_episodes()
    assert result == 0


@pytest.mark.asyncio
async def test_extract_skills_throttled_returns_zero(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    sx._LAST_RUN = datetime.now(UTC)

    result = await extract_skills_from_recent_episodes()
    assert result == 0

    sx._LAST_RUN = None  # restore


@pytest.mark.asyncio
async def test_extract_skills_returns_zero_when_no_qualifying_episodes(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    sx._LAST_RUN = None
    monkeypatch.setattr(sx._db, "fetch", AsyncMock(return_value=[]))

    result = await extract_skills_from_recent_episodes()
    assert result == 0


@pytest.mark.asyncio
async def test_extract_skills_returns_count_of_processed_episodes(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    sx._LAST_RUN = None
    monkeypatch.setattr(
        sx._db, "fetch", AsyncMock(return_value=[_GOOD_EPISODE, _GOOD_EPISODE])
    )
    monkeypatch.setattr(sx, "maybe_extract_skill", AsyncMock(return_value=_SKILL_ID))

    result = await extract_skills_from_recent_episodes()
    assert result == 2

    sx._LAST_RUN = None  # restore


@pytest.mark.asyncio
async def test_extract_skills_handles_partial_failures(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    sx._LAST_RUN = None
    monkeypatch.setattr(
        sx._db, "fetch", AsyncMock(return_value=[_GOOD_EPISODE, _GOOD_EPISODE])
    )
    # First call returns skill_id, second returns None (failed)
    monkeypatch.setattr(
        sx, "maybe_extract_skill", AsyncMock(side_effect=[_SKILL_ID, None])
    )

    result = await extract_skills_from_recent_episodes()
    assert result == 1

    sx._LAST_RUN = None  # restore


@pytest.mark.asyncio
async def test_extract_skills_returns_zero_on_fetch_error(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", object())
    sx._LAST_RUN = None
    monkeypatch.setattr(
        sx._db, "fetch", AsyncMock(side_effect=RuntimeError("db timeout"))
    )

    result = await extract_skills_from_recent_episodes()
    assert result == 0

    sx._LAST_RUN = None  # restore


# ── helpers ───────────────────────────────────────────────────────────────────


class _async_ctx:
    """Minimal async context manager wrapping a mock connection."""

    def __init__(self, conn):
        self._conn = conn

    def __await__(self):
        return self.__aenter__().__await__()

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass
