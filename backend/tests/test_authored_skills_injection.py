"""
Tests for authored-skill injection:
  - skill_extractor.search_authored_skills (vector + fulltext paths)
  - guardrails.authored_skills_section (formatting)
  - system_prompt.build_system_prompt (authored_skills parameter)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.agent.skill_extractor as sx
from app.agent.skill_extractor import search_authored_skills
from app.agent.prompts.guardrails import authored_skills_section
from app.agent.prompts.system_prompt import build_system_prompt

_SKILL = {
    "name": "Analyse CSV and generate chart",
    "pattern": "Load a CSV, aggregate rows, render a bar chart.",
    "solution": "Use pandas read_csv, groupby, then matplotlib savefig.",
    "preconditions": ["CSV file is accessible"],
    "gotchas": ["Check for empty rows before aggregating"],
    "use_count": 4,
    "success_count": 4,
}


# ── search_authored_skills ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_pool(monkeypatch):
    monkeypatch.setattr(sx._db, "db_pool", None)
    result = await search_authored_skills("analyse my data")
    assert result == []


@pytest.mark.asyncio
async def test_search_uses_vector_path_when_embedding_available(monkeypatch):
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=[0.1] * 1536))

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[_SKILL])
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_async_ctx(mock_conn))
    monkeypatch.setattr(sx._db, "db_pool", mock_pool)

    result = await search_authored_skills("analyse my data", user_id="default")

    assert len(result) == 1
    assert result[0]["name"] == _SKILL["name"]
    mock_conn.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_falls_back_to_fulltext_when_no_embedding(monkeypatch):
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=None))
    monkeypatch.setattr(sx._db, "db_pool", object())
    monkeypatch.setattr(sx._db, "fetch", AsyncMock(return_value=[_SKILL]))

    result = await search_authored_skills("analyse my data", user_id="default")

    assert len(result) == 1
    sx._db.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_falls_back_to_fulltext_on_vector_error(monkeypatch):
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=[0.1] * 1536))

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=RuntimeError("ivfflat unavailable"))
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_async_ctx(mock_conn))
    monkeypatch.setattr(sx._db, "db_pool", mock_pool)
    monkeypatch.setattr(sx._db, "fetch", AsyncMock(return_value=[_SKILL]))

    result = await search_authored_skills("analyse my data")

    assert len(result) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_on_fulltext_error(monkeypatch):
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=None))
    monkeypatch.setattr(sx._db, "db_pool", object())
    monkeypatch.setattr(sx._db, "fetch", AsyncMock(side_effect=RuntimeError("db down")))

    result = await search_authored_skills("analyse my data")
    assert result == []


@pytest.mark.asyncio
async def test_search_respects_limit(monkeypatch):
    monkeypatch.setattr(sx, "_embed", AsyncMock(return_value=None))
    monkeypatch.setattr(sx._db, "db_pool", object())

    captured_limit: list[int] = []

    async def fake_fetch(sql, *args):
        captured_limit.append(args[-1])  # limit is last positional arg
        return []

    monkeypatch.setattr(sx._db, "fetch", fake_fetch)

    await search_authored_skills("query", limit=5)
    assert captured_limit[0] == 5


# ── authored_skills_section ───────────────────────────────────────────────────


def test_authored_skills_section_returns_empty_for_no_skills():
    assert authored_skills_section([]) == ""


def test_authored_skills_section_contains_skill_name():
    result = authored_skills_section([_SKILL])
    assert _SKILL["name"] in result


def test_authored_skills_section_contains_pattern():
    result = authored_skills_section([_SKILL])
    assert _SKILL["pattern"] in result


def test_authored_skills_section_contains_solution_snippet():
    result = authored_skills_section([_SKILL])
    # Solution is truncated to 400 chars; our fixture is shorter than that
    assert "pandas" in result


def test_authored_skills_section_contains_preconditions():
    result = authored_skills_section([_SKILL])
    assert "CSV file is accessible" in result


def test_authored_skills_section_contains_gotchas():
    result = authored_skills_section([_SKILL])
    assert "empty rows" in result


def test_authored_skills_section_contains_usage_stats():
    result = authored_skills_section([_SKILL])
    assert "4×" in result
    assert "100%" in result


def test_authored_skills_section_skips_skill_with_empty_name():
    bad = {**_SKILL, "name": ""}
    result = authored_skills_section([bad])
    # Section header still present but no skill bullet
    assert "•" not in result


def test_authored_skills_section_truncates_long_solution():
    long_skill = {**_SKILL, "solution": "x" * 600}
    result = authored_skills_section([long_skill])
    # 400 char truncation — the full 600-char string should not appear
    assert "x" * 600 not in result
    assert "x" * 400 in result


def test_authored_skills_section_handles_none_lists():
    skill_no_lists = {**_SKILL, "preconditions": None, "gotchas": None}
    result = authored_skills_section([skill_no_lists])
    assert _SKILL["name"] in result


def test_authored_skills_section_zero_use_count_omits_stats():
    skill_unused = {**_SKILL, "use_count": 0, "success_count": 0}
    result = authored_skills_section([skill_unused])
    assert "×" not in result


# ── build_system_prompt integration ──────────────────────────────────────────


def test_build_system_prompt_injects_authored_skills():
    result = build_system_prompt(
        retrieved_context=None,
        extra_context=None,
        persona_prompt="",
        authored_skills=[_SKILL],
    )
    assert "<learned_skills>" in result
    assert _SKILL["name"] in result


def test_build_system_prompt_no_section_when_skills_empty():
    result = build_system_prompt(
        retrieved_context=None,
        extra_context=None,
        persona_prompt="",
        authored_skills=[],
    )
    assert "<learned_skills>" not in result


def test_build_system_prompt_no_section_when_skills_none():
    result = build_system_prompt(
        retrieved_context=None,
        extra_context=None,
        persona_prompt="",
        authored_skills=None,
    )
    assert "<learned_skills>" not in result


def test_build_system_prompt_skills_appear_after_retrieved_context():
    result = build_system_prompt(
        retrieved_context="some memory",
        extra_context=None,
        persona_prompt="",
        authored_skills=[_SKILL],
    )
    ctx_pos = result.index("<retrieved_context>")
    skills_pos = result.index("<learned_skills>")
    assert skills_pos > ctx_pos


def test_build_system_prompt_skills_appear_before_extra_context():
    result = build_system_prompt(
        retrieved_context=None,
        extra_context="some tool hint",
        persona_prompt="",
        authored_skills=[_SKILL],
    )
    skills_pos = result.index("<learned_skills>")
    extra_pos = result.index("some tool hint")
    assert skills_pos < extra_pos


# ── helpers ───────────────────────────────────────────────────────────────────


class _async_ctx:
    def __init__(self, conn):
        self._conn = conn

    def __await__(self):
        return self.__aenter__().__await__()

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass
