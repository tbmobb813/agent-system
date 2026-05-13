"""skill_registry DB helpers."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

import app.agent.skill_registry as sr


@pytest.fixture(autouse=True)
def _restore_last_update():
    prev = sr._LAST_UPDATE
    sr._LAST_UPDATE = None
    yield
    sr._LAST_UPDATE = prev


@pytest.mark.asyncio
async def test_update_skills_no_pool(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", None)
    await sr.update_skills()


@pytest.mark.asyncio
async def test_update_skills_throttled(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    sr._LAST_UPDATE = datetime.now(UTC)
    called = []

    async def _fetch(*_a, **_k):
        called.append(True)
        return []

    monkeypatch.setattr(sr._db, "fetch", _fetch)
    await sr.update_skills()
    assert called == []


@pytest.mark.asyncio
async def test_update_skills_primary_fetch_raises(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    monkeypatch.setattr(sr._db, "fetch", AsyncMock(side_effect=RuntimeError("db")))
    await sr.update_skills()


@pytest.mark.asyncio
async def test_update_skills_upserts_and_tool_fetch_fails(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    events = [
        {"query": "write a draft email", "status": "completed", "tool_calls_count": 0}
    ] * 3

    fetch_calls = 0

    async def fetch_side(q: str, *_a, **_k):
        nonlocal fetch_calls
        fetch_calls += 1
        if "JOIN tasks t ON t.id::text = tc.task_id" in q.replace("\n", " "):
            raise RuntimeError("no joins")
        if "GROUP BY t.id, t.query" in q.replace("\n", " "):
            return events
        raise AssertionError("unexpected fetch")

    executes: list[str] = []

    async def execute_side(q: str, *_args):
        executes.append(q)

    monkeypatch.setattr(sr._db, "fetch", fetch_side)
    monkeypatch.setattr(sr._db, "execute", execute_side)

    await sr.update_skills()
    assert any("INSERT INTO skills" in q for q in executes)
    assert fetch_calls >= 1


@pytest.mark.asyncio
async def test_update_skills_upsert_row_fails_logged(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    events = [
        {
            "query": "cron workflow automation",
            "status": "completed",
            "tool_calls_count": 0,
        }
    ] * 3

    async def fetch_side(q: str, *_a, **_k):
        if "GROUP BY t.id, t.query" in q.replace("\n", " "):
            return events
        if "JOIN tasks t ON t.id::text = tc.task_id" in q.replace("\n", " "):
            return []
        raise AssertionError(q[:120])

    async def execute_side(_q: str, *_args):
        raise RuntimeError("no table skills")

    monkeypatch.setattr(sr._db, "fetch", fetch_side)
    monkeypatch.setattr(sr._db, "execute", execute_side)
    await sr.update_skills()


@pytest.mark.asyncio
async def test_get_agent_profile_fetch_error(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    monkeypatch.setattr(sr._db, "fetch", AsyncMock(side_effect=RuntimeError("x")))
    out = await sr.get_agent_profile()
    assert out == {"skills": [], "growth_areas": []}


@pytest.mark.asyncio
async def test_get_agent_profile_partitions(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())
    rows = [
        {
            "task_type": "writing",
            "skill_name": "Writing",
            "success_rate": 0.92,
            "total_uses": 10,
            "proficiency_level": "expert",
            "required_tools": json.dumps([]),
            "last_computed": datetime.now(UTC),
        },
        {
            "task_type": "research",
            "skill_name": "Research",
            "success_rate": 0.5,
            "total_uses": 5,
            "proficiency_level": "novice",
            "required_tools": json.dumps(["web_search"]),
            "last_computed": None,
        },
    ]

    monkeypatch.setattr(sr._db, "fetch", AsyncMock(return_value=rows))
    body = await sr.get_agent_profile()
    types_ok = {e["task_type"] for e in body["skills"]}
    types_ga = {e["task_type"] for e in body["growth_areas"]}
    assert "writing" in types_ok
    assert "research" in types_ga


@pytest.mark.asyncio
async def test_update_skills_sample_too_sparse_skips_upsert(monkeypatch):
    monkeypatch.setattr(sr._db, "db_pool", object())

    async def fetch_side(q: str, *_a, **_k):
        if "GROUP BY t.id, t.query" in q.replace("\n", " "):
            return [
                {"query": "tiny", "status": "completed", "tool_calls_count": 0},
            ]
        if "JOIN tasks t ON t.id::text = tc.task_id" in q.replace("\n", " "):
            return []
        raise AssertionError(q[:120])

    executed = []

    async def execute_side(q: str, *_a):
        executed.append(q)

    monkeypatch.setattr(sr._db, "fetch", fetch_side)
    monkeypatch.setattr(sr._db, "execute", execute_side)

    await sr.update_skills()
    assert executed == []
