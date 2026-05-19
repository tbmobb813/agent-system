from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.user_model import (
    UserModelManager,
    _build_memory_block,
    _MAX_MEMORY_CHARS,
)


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, *args):
        pass


# ── _build_memory_block ───────────────────────────────────────────────────────


def test_build_memory_block_formats_lines():
    memories = [
        {"category": "fact", "content": "user is a software engineer"},
        {"category": "preference", "content": "user prefers dark mode"},
    ]
    block = _build_memory_block(memories)
    assert "[fact] user is a software engineer" in block
    assert "[preference] user prefers dark mode" in block


def test_build_memory_block_truncates_at_char_limit():
    long_content = "x" * (_MAX_MEMORY_CHARS + 100)
    memories = [{"category": "fact", "content": long_content}]
    block = _build_memory_block(memories)
    assert len(block) == 0  # first entry already exceeds limit


def test_build_memory_block_stops_adding_when_limit_reached():
    entry = "a" * 500
    memories = [{"category": "fact", "content": entry} for _ in range(20)]
    block = _build_memory_block(memories)
    assert len(block) <= _MAX_MEMORY_CHARS + 20  # small slack for labels


def test_build_memory_block_falls_back_to_fact_category():
    memories = [{"content": "some fact"}]
    block = _build_memory_block(memories)
    assert "[fact]" in block


# ── UserModelManager.get ──────────────────────────────────────────────────────


async def test_get_returns_empty_string_when_no_db(monkeypatch):
    monkeypatch.setattr("app.agent.user_model._db.db_pool", None)
    mgr = UserModelManager()
    result = await mgr.get()
    assert result == ""


async def test_get_returns_model_text_from_db(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(
        return_value={"model_text": "The user is a developer."}
    )
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)
    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)

    mgr = UserModelManager()
    result = await mgr.get("u1")
    assert result == "The user is a developer."


async def test_get_returns_empty_when_no_row(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value=None)
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)
    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)

    mgr = UserModelManager()
    result = await mgr.get("u1")
    assert result == ""


async def test_get_returns_empty_on_db_exception(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(side_effect=RuntimeError("db error"))
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)
    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)

    mgr = UserModelManager()
    result = await mgr.get("u1")
    assert result == ""


# ── UserModelManager.run_dialectic_reflection ─────────────────────────────────


async def test_reflection_skips_when_flag_disabled(monkeypatch):
    monkeypatch.setattr("app.agent.user_model._db.db_pool", object())
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", False)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "key")

    mgr = UserModelManager()
    get_mock = AsyncMock()
    monkeypatch.setattr(mgr, "get", get_mock)

    await mgr.run_dialectic_reflection("u1")
    get_mock.assert_not_awaited()


async def test_reflection_skips_when_no_db(monkeypatch):
    monkeypatch.setattr("app.agent.user_model._db.db_pool", None)
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", True)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "key")

    mgr = UserModelManager()
    await mgr.run_dialectic_reflection("u1")  # should not raise


async def test_reflection_skips_when_no_api_key(monkeypatch):
    monkeypatch.setattr("app.agent.user_model._db.db_pool", object())
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", True)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "")

    mgr = UserModelManager()
    await mgr.run_dialectic_reflection("u1")  # should not raise


async def test_reflection_skips_when_cooldown_active(monkeypatch):
    recent_time = datetime.now(UTC) - timedelta(minutes=5)

    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value={"updated_at": recent_time})
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", True)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "key")

    mgr = UserModelManager()
    get_mock = AsyncMock(return_value="")
    monkeypatch.setattr(mgr, "get", get_mock)

    await mgr.run_dialectic_reflection("u1")
    get_mock.assert_not_awaited()


async def test_reflection_skips_when_too_few_memories(monkeypatch):
    old_time = datetime.now(UTC) - timedelta(hours=2)

    cooldown_conn = AsyncMock()
    cooldown_conn.fetchrow = AsyncMock(return_value={"updated_at": old_time})

    mem_conn = AsyncMock()
    mem_conn.fetch = AsyncMock(return_value=[{"category": "fact", "content": "x"}])

    call_count = 0

    class MultiConn:
        async def __aenter__(self):
            nonlocal call_count
            call_count += 1
            return cooldown_conn if call_count == 1 else mem_conn

        async def __aexit__(self, *args):
            pass

    fake_pool = MagicMock()
    fake_pool.acquire = lambda: MultiConn()

    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", True)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "key")

    mgr = UserModelManager()
    get_mock = AsyncMock(return_value="")
    monkeypatch.setattr(mgr, "get", get_mock)

    await mgr.run_dialectic_reflection("u1")
    # Not enough memories (1 < 5), so get should not be called (LLM path not reached)
    get_mock.assert_not_awaited()


async def test_reflection_upserts_model_text(monkeypatch):
    old_time = datetime.now(UTC) - timedelta(hours=2)
    memories = [{"category": "fact", "content": f"memory {i}"} for i in range(6)]

    call_count = 0

    class MultiConn:
        async def __aenter__(self):
            nonlocal call_count
            call_count += 1
            conn = AsyncMock()
            if call_count == 1:
                conn.fetchrow = AsyncMock(return_value={"updated_at": old_time})
            elif call_count == 2:
                conn.fetch = AsyncMock(return_value=memories)
            else:
                conn.execute = AsyncMock()
            return conn

        async def __aexit__(self, *args):
            pass

    fake_pool = MagicMock()
    fake_pool.acquire = lambda: MultiConn()

    monkeypatch.setattr("app.agent.user_model._db.db_pool", fake_pool)
    monkeypatch.setattr("app.config.settings.AGENT_DIALECTIC_REFLECTION", True)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "key")
    monkeypatch.setattr(
        "app.config.settings.OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    monkeypatch.setattr("app.config.settings.SITE_URL", "https://example.com")
    monkeypatch.setattr("app.config.settings.DEFAULT_MODEL_SIMPLE", "test-model")

    fake_choice = MagicMock()
    fake_choice.message.content = "The user is a developer who prefers concise answers."
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]

    fake_client = AsyncMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    fake_openai_cls = MagicMock(return_value=fake_client)

    mgr = UserModelManager()
    get_mock = AsyncMock(return_value="")
    monkeypatch.setattr(mgr, "get", get_mock)

    import sys

    fake_openai_mod = MagicMock()
    fake_openai_mod.AsyncOpenAI = fake_openai_cls
    monkeypatch.setitem(sys.modules, "openai", fake_openai_mod)

    await mgr.run_dialectic_reflection("u1")

    fake_client.chat.completions.create.assert_awaited_once()
