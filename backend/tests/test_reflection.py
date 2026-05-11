"""Tests for app/agent/reflection.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agent.reflection as ref_mod
from app.agent.reflection import post_task_reflection


def _make_completion(content: str):
    choice = MagicMock()
    choice.message.content = content
    comp = MagicMock()
    comp.choices = [choice]
    return comp


# ── early-exit guards ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflection_skips_when_no_api_key():
    with patch.object(ref_mod.settings, "OPENROUTER_API_KEY", ""):
        await post_task_reflection("t1", "query", "result")


@pytest.mark.asyncio
async def test_reflection_handles_llm_exception():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("network error"))
    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
    ):
        await post_task_reflection("t1", "query", "result")  # must not raise


# ── happy path: reflection with structured JSON ───────────────────────────────


@pytest.mark.asyncio
async def test_reflection_persists_when_db_available():
    reflection_text = (
        "1. Went well.\n2. Could improve.\n3. Do better.\n4. Yes.\n5. Confidence: 8.\n"
        "```json\n"
        '{"self_rating": 8, "learned_rules": ["Always verify syntax", "Use web_search for unknown APIs"]}\n'
        "```"
    )
    comp = _make_completion(reflection_text)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_pool = MagicMock()
    mock_execute = AsyncMock()

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", mock_execute),
    ):
        await post_task_reflection(
            task_id="task-99",
            query="Write a Python function",
            result="def foo(): pass",
            success=True,
            model_used="gpt-4",
            tools_used=["code_runner"],
            user_id="user-1",
        )

    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_reflection_promotes_learned_rules_to_memory():
    reflection_text = (
        "Analysis...\n"
        "```json\n"
        '{"self_rating": 7, "learned_rules": ["Use streaming for long tasks"]}\n'
        "```"
    )
    comp = _make_completion(reflection_text)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_memory = MagicMock()
    mock_memory.save = AsyncMock()
    mock_execute = AsyncMock()
    mock_pool = MagicMock()

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", mock_execute),
        patch("app.agent.memory.memory_manager", mock_memory),
    ):
        await post_task_reflection("t2", "query", "result", user_id="u1")

    mock_memory.save.assert_awaited_once()
    call_kwargs = mock_memory.save.call_args.kwargs
    assert "Learned rule" in call_kwargs["content"]
    assert call_kwargs["category"] == "pattern"


@pytest.mark.asyncio
async def test_reflection_clamps_self_rating():
    reflection_text = '```json\n{"self_rating": 99, "learned_rules": []}\n```'
    comp = _make_completion(reflection_text)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_pool = MagicMock()
    captured = {}

    async def capture_execute(sql, *args):
        captured["args"] = args

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", capture_execute),
    ):
        await post_task_reflection("t3", "q", "r")

    # self_rating is the 7th positional arg to execute (index 6 after sql)
    self_rating = captured["args"][6]
    assert self_rating == 10  # clamped from 99


@pytest.mark.asyncio
async def test_reflection_handles_non_json_response():
    comp = _make_completion("Great job overall! No JSON here.")
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_pool = MagicMock()
    mock_execute = AsyncMock()

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", mock_execute),
    ):
        await post_task_reflection("t4", "query", "result")

    # Should still persist reflection_text even without JSON block
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_reflection_db_failure_does_not_raise():
    comp = _make_completion(
        'Some reflection ```json\n{"self_rating": 5, "learned_rules": []}\n```'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_pool = MagicMock()

    async def fail_execute(*a, **kw):
        raise Exception("db error")

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", fail_execute),
    ):
        await post_task_reflection("t5", "q", "r")  # must not raise


@pytest.mark.asyncio
async def test_reflection_skips_short_rules():
    reflection_text = (
        "```json\n"
        '{"self_rating": 6, "learned_rules": ["ok", "Use streaming for long tasks that may time out"]}\n'
        "```"
    )
    comp = _make_completion(reflection_text)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=comp)

    mock_memory = MagicMock()
    mock_memory.save = AsyncMock()
    mock_pool = MagicMock()
    mock_execute = AsyncMock()

    with (
        patch.object(ref_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch("app.agent.reflection._openrouter_client", return_value=client),
        patch.object(ref_mod._db, "db_pool", mock_pool),
        patch.object(ref_mod._db, "execute", mock_execute),
        patch("app.agent.memory.memory_manager", mock_memory),
    ):
        await post_task_reflection("t6", "q", "r")

    # "ok" is < 10 chars and should be skipped; only the long rule saved
    assert mock_memory.save.await_count == 1
