"""Tests for app/agent/episodes.py"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agent.episodes as ep_mod
from app.agent.episodes import _backfill_embedding, _embed, save_episode

_FAKE_UUID = "550e8400-e29b-41d4-a716-446655440000"


# ── save_episode ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_episode_returns_none_when_no_pool(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", None)
    result = await save_episode(
        task_id=_FAKE_UUID,
        user_id="default",
        query="test query",
        outcome="test outcome",
        success=True,
        tools_used=["web_search"],
        duration_ms=1000,
    )
    assert result is None


@pytest.mark.asyncio
async def test_save_episode_returns_episode_id(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod._db, "fetchrow", AsyncMock(return_value={"id": _FAKE_UUID})
    )
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: coro.close() or None
    )

    result = await save_episode(
        task_id=_FAKE_UUID,
        user_id="default",
        query="q",
        outcome="o",
        success=True,
        tools_used=[],
        duration_ms=500,
    )
    assert result == _FAKE_UUID


@pytest.mark.asyncio
async def test_save_episode_passes_correct_args_to_insert(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: coro.close() or None
    )

    captured: list[tuple] = []

    async def fake_fetchrow(sql, *args):
        captured.append(args)
        return {"id": _FAKE_UUID}

    monkeypatch.setattr(ep_mod._db, "fetchrow", fake_fetchrow)

    await save_episode(
        task_id=_FAKE_UUID,
        user_id="u1",
        query="my query",
        outcome="my outcome",
        success=False,
        tools_used=["web_search", "code_execution"],
        duration_ms=2500,
        cost_usd=0.0042,
    )

    assert len(captured) == 1
    args = captured[0]
    assert args[0] == "u1"  # user_id
    assert args[1] == _FAKE_UUID  # task_id
    assert args[2] == "my query"  # query
    assert args[3] == "my outcome"  # outcome
    assert args[4] is False  # success
    assert "web_search" in args[5]  # tools_used
    assert "code_execution" in args[5]
    assert args[6] == 0.0042  # cost_usd
    assert args[7] == 2500  # duration_ms


@pytest.mark.asyncio
async def test_save_episode_deduplicates_tools_used(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: coro.close() or None
    )

    captured: list[list] = []

    async def fake_fetchrow(sql, *args):
        captured.append(list(args[5]))  # tools_used is args[5]
        return {"id": _FAKE_UUID}

    monkeypatch.setattr(ep_mod._db, "fetchrow", fake_fetchrow)

    await save_episode(
        task_id=_FAKE_UUID,
        user_id=None,
        query="q",
        outcome="o",
        success=True,
        tools_used=["web_search", "web_search", "code_execution", "web_search"],
        duration_ms=100,
    )

    assert captured[0] == ["web_search", "code_execution"]


@pytest.mark.asyncio
async def test_save_episode_truncates_long_outcome(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: coro.close() or None
    )

    captured: list[str] = []

    async def fake_fetchrow(sql, *args):
        captured.append(args[3])  # outcome is args[3]
        return {"id": _FAKE_UUID}

    monkeypatch.setattr(ep_mod._db, "fetchrow", fake_fetchrow)

    long_outcome = "x" * 5000
    await save_episode(
        task_id=_FAKE_UUID,
        user_id=None,
        query="q",
        outcome=long_outcome,
        success=True,
        tools_used=[],
        duration_ms=100,
    )

    assert len(captured[0]) == 4000


@pytest.mark.asyncio
async def test_save_episode_none_cost_usd_passed_through(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: coro.close() or None
    )

    captured: list = []

    async def fake_fetchrow(sql, *args):
        captured.append(args[6])  # cost_usd is args[6]
        return {"id": _FAKE_UUID}

    monkeypatch.setattr(ep_mod._db, "fetchrow", fake_fetchrow)

    await save_episode(
        task_id=_FAKE_UUID,
        user_id=None,
        query="q",
        outcome="o",
        success=True,
        tools_used=[],
        duration_ms=100,
    )

    assert captured[0] is None


@pytest.mark.asyncio
async def test_save_episode_returns_none_on_insert_error(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod._db, "fetchrow", AsyncMock(side_effect=RuntimeError("db down"))
    )

    result = await save_episode(
        task_id=_FAKE_UUID,
        user_id=None,
        query="q",
        outcome="o",
        success=True,
        tools_used=[],
        duration_ms=100,
    )
    assert result is None


@pytest.mark.asyncio
async def test_save_episode_schedules_backfill_task(monkeypatch):
    monkeypatch.setattr(ep_mod._db, "db_pool", object())
    monkeypatch.setattr(
        ep_mod._db, "fetchrow", AsyncMock(return_value={"id": _FAKE_UUID})
    )

    scheduled = []
    monkeypatch.setattr(
        ep_mod.asyncio, "create_task", lambda coro: scheduled.append(coro) or None
    )

    await save_episode(
        task_id=_FAKE_UUID,
        user_id=None,
        query="q",
        outcome="o",
        success=True,
        tools_used=[],
        duration_ms=100,
    )

    assert len(scheduled) == 1
    # Clean up the coroutine to avoid ResourceWarning
    scheduled[0].close()


# ── _backfill_embedding ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_embedding_skips_when_embed_returns_none(monkeypatch):
    monkeypatch.setattr(ep_mod, "_embed", AsyncMock(return_value=None))
    execute_mock = AsyncMock()
    monkeypatch.setattr(ep_mod._db, "execute", execute_mock)

    await _backfill_embedding(_FAKE_UUID, "query", "outcome")

    execute_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_embedding_updates_row_with_embedding(monkeypatch):
    fake_vector = [0.1] * 1536
    monkeypatch.setattr(ep_mod, "_embed", AsyncMock(return_value=fake_vector))

    captured: list[tuple] = []

    async def fake_execute(sql, *args):
        captured.append(args)

    monkeypatch.setattr(ep_mod._db, "execute", fake_execute)

    await _backfill_embedding(_FAKE_UUID, "query text", "outcome text")

    assert len(captured) == 1
    assert captured[0][0] == fake_vector  # embedding
    assert captured[0][1] == _FAKE_UUID  # episode_id


@pytest.mark.asyncio
async def test_backfill_embedding_handles_update_failure(monkeypatch):
    monkeypatch.setattr(ep_mod, "_embed", AsyncMock(return_value=[0.0] * 1536))
    monkeypatch.setattr(
        ep_mod._db, "execute", AsyncMock(side_effect=RuntimeError("write failed"))
    )

    # Should not raise
    await _backfill_embedding(_FAKE_UUID, "q", "o")


# ── _embed ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.setattr(ep_mod.settings, "OPENAI_API_KEY", "")
    result = await _embed("some text")
    assert result is None


@pytest.mark.asyncio
async def test_embed_returns_none_on_api_error(monkeypatch):
    monkeypatch.setattr(ep_mod.settings, "OPENAI_API_KEY", "sk-test")

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(
        side_effect=RuntimeError("quota exceeded")
    )
    monkeypatch.setattr(ep_mod, "_get_embed_client", lambda: mock_client)
    # Reset cached client so _get_embed_client is called fresh
    monkeypatch.setattr(ep_mod, "_embed_client", None)

    result = await _embed("some text")
    assert result is None


@pytest.mark.asyncio
async def test_embed_returns_vector_on_success(monkeypatch):
    monkeypatch.setattr(ep_mod.settings, "OPENAI_API_KEY", "sk-test")

    fake_vector = [0.5] * 1536
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_vector)]

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(ep_mod, "_get_embed_client", lambda: mock_client)
    monkeypatch.setattr(ep_mod, "_embed_client", None)

    result = await _embed("some text")
    assert result == fake_vector
