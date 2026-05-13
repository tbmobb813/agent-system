"""Schedules API with DB mocked."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytest.importorskip("croniter")

AUTH = {"Authorization": "Bearer sk-agent-local-dev"}
SCHED_PREFIX = "/agent/schedules"

_NICE_CRON = "0 9 * * *"


@pytest.mark.asyncio
async def test_schedules_require_db(monkeypatch):
    monkeypatch.setattr("app.routes.schedules._db.db_pool", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get(SCHED_PREFIX, headers=AUTH)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_schedules_create_and_list_and_delete(monkeypatch):
    monkeypatch.setattr("app.routes.schedules._db.db_pool", object())
    sid = uuid4()
    next_at = datetime.now(UTC)
    row_single = {
        "id": sid,
        "next_run_at": next_at,
        "user_id": "u1",
        "cron_expr": _NICE_CRON,
        "prompt": "hi",
        "context": None,
        "router_tier": "simple",
        "max_iterations": 5,
        "enabled": True,
        "last_run_at": None,
        "created_at": next_at,
    }

    async def fetchrow(q: str, *args):
        ql = q.upper()
        if "INSERT" in ql:
            return {"id": sid, "next_run_at": next_at}
        if "DELETE" in ql:
            return {"id": sid}
        raise AssertionError(q[:80])

    async def fetch(q: str, *args):
        if "FROM scheduled_tasks" in q and "LIMIT" in q:
            return [row_single]
        raise AssertionError(q[:80])

    monkeypatch.setattr(
        "app.routes.schedules.fetchrow", AsyncMock(side_effect=fetchrow)
    )
    monkeypatch.setattr("app.routes.schedules.fetch", AsyncMock(side_effect=fetch))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        c = await client.post(
            SCHED_PREFIX,
            headers=AUTH,
            json={
                "cron": _NICE_CRON,
                "prompt": "ping",
                "user_id": "u1",
                "max_iterations": 5,
                "router_tier": "simple",
            },
        )
        assert c.status_code == 200
        body = c.json()
        assert "id" in body and "next_run_at" in body

        lst = await client.get(SCHED_PREFIX, params={"user_id": "u1"}, headers=AUTH)
        assert lst.status_code == 200
        assert lst.json()[0]["prompt"] == "hi"

        d = await client.delete(
            f"{SCHED_PREFIX}/{sid}", params={"user_id": "u1"}, headers=AUTH
        )
        assert d.status_code == 200


@pytest.mark.asyncio
async def test_schedules_invalid_cron(monkeypatch):
    monkeypatch.setattr("app.routes.schedules._db.db_pool", object())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.post(
            SCHED_PREFIX,
            headers=AUTH,
            json={
                "cron": "totally-invalid-cron-!!!",
                "prompt": "nope",
                "enabled": True,
            },
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_schedule_delete_missing(monkeypatch):
    monkeypatch.setattr("app.routes.schedules._db.db_pool", object())
    monkeypatch.setattr("app.routes.schedules.fetchrow", AsyncMock(return_value=None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.delete(
            f"{SCHED_PREFIX}/{uuid4()}",
            headers=AUTH,
        )
    assert r.status_code == 404
