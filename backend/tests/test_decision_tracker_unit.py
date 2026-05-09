import pytest

import app.agent.decision_tracker as dt


@pytest.mark.asyncio
async def test_log_decision_no_db(monkeypatch):
    monkeypatch.setattr(dt._db, "db_pool", None)
    await dt.log_decision("t", "pick", "m1")
    await dt.mark_outcome("t", "success")


@pytest.mark.asyncio
async def test_log_decision_insert(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    async def _exe(q: str, *args):
        calls.append((q, args))

    monkeypatch.setattr(dt._db, "db_pool", object())
    monkeypatch.setattr(dt._db, "execute", _exe)

    await dt.log_decision(
        "task-1",
        "model_selection",
        "x" * 600,
        reasoning="why" * 400,
        confidence=99.0,
        options=["a", "b"],
        user_id="u",
    )
    await dt.mark_outcome("task-1", "failure")
    assert any("INSERT INTO decisions" in q for q, _ in calls)
    assert any("UPDATE decisions" in q for q, _ in calls)


@pytest.mark.asyncio
async def test_log_decision_execute_swallows(monkeypatch):
    async def boom(_q, *_a):
        raise RuntimeError("fail")

    monkeypatch.setattr(dt._db, "db_pool", object())
    monkeypatch.setattr(dt._db, "execute", boom)
    await dt.log_decision("t", "p", "c")
    await dt.mark_outcome("t", "success")
