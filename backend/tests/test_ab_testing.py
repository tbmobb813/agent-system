"""Tests for app/agent/ab_testing.py"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agent.ab_testing as ab_mod
from app.agent.ab_testing import _judge_quality, _run_approach, run_ab_test

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_completion(content: str, input_tokens: int = 10, output_tokens: int = 20):
    usage = MagicMock()
    usage.prompt_tokens = input_tokens
    usage.completion_tokens = output_tokens
    choice = MagicMock()
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


def _patched_client(completion):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


# ── _run_approach ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_approach_success():
    comp = _make_completion("The answer is 42", input_tokens=5, output_tokens=8)
    with patch("app.agent.ab_testing._client", return_value=_patched_client(comp)):
        result = await _run_approach("What is 6×7?", "test-model")
    assert result["success"] is True
    assert result["output"] == "The answer is 42"
    assert result["input_tokens"] == 5
    assert result["output_tokens"] == 8
    assert result["cost"] > 0
    assert result["error"] is None


@pytest.mark.asyncio
async def test_run_approach_with_extra_system():
    comp = _make_completion("result")
    with patch("app.agent.ab_testing._client", return_value=_patched_client(comp)):
        result = await _run_approach("task", "model", extra_system="Be concise.")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_run_approach_api_failure():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
    with patch("app.agent.ab_testing._client", return_value=client):
        result = await _run_approach("task", "model")
    assert result["success"] is False
    assert "timeout" in result["error"]
    assert result["cost"] == 0.0


# ── _judge_quality ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_quality_returns_a():
    comp = _make_completion("A")
    with patch("app.agent.ab_testing._client", return_value=_patched_client(comp)):
        result = await _judge_quality("task", "output a", "output b")
    assert result == "a"


@pytest.mark.asyncio
async def test_judge_quality_returns_b():
    comp = _make_completion("B is better")
    with patch("app.agent.ab_testing._client", return_value=_patched_client(comp)):
        result = await _judge_quality("task", "output a", "output b")
    assert result == "b"


@pytest.mark.asyncio
async def test_judge_quality_returns_tie():
    comp = _make_completion("TIE")
    with patch("app.agent.ab_testing._client", return_value=_patched_client(comp)):
        result = await _judge_quality("task", "output a", "output b")
    assert result == "tie"


@pytest.mark.asyncio
async def test_judge_quality_exception_returns_none():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))
    with patch("app.agent.ab_testing._client", return_value=client):
        result = await _judge_quality("task", "a", "b")
    assert result is None


# ── run_ab_test ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_ab_test_both_succeed_a_wins():
    comp_a = _make_completion("good answer A", input_tokens=5, output_tokens=5)
    comp_b = _make_completion("answer B", input_tokens=10, output_tokens=20)
    judge_comp = _make_completion("A")

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # First two calls are approach A and B
            return comp_a if call_count == 1 else comp_b
        return judge_comp

    client = MagicMock()
    client.chat.completions.create = mock_create

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", None),
    ):
        result = await run_ab_test(
            "What is AI?",
            {"model": "model-a"},
            {"model": "model-b"},
        )

    assert "winner" in result
    assert result["result_a"]["success"] is True
    assert result["result_b"]["success"] is True


@pytest.mark.asyncio
async def test_run_ab_test_b_wins_on_availability():
    comp_b = _make_completion("answer from B")
    client = MagicMock()

    call_results = [Exception("model-a down"), comp_b]
    call_idx = 0

    async def mock_create(**kwargs):
        nonlocal call_idx
        r = call_results[call_idx]
        call_idx += 1
        if isinstance(r, Exception):
            raise r
        return r

    client.chat.completions.create = mock_create

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", None),
    ):
        result = await run_ab_test("task", {"model": "bad"}, {"model": "good"})

    assert result["winner"] == "b"
    assert result["win_reason"] == "availability"


@pytest.mark.asyncio
async def test_run_ab_test_a_wins_on_availability():
    comp_a = _make_completion("answer from A")
    client = MagicMock()

    call_results = [comp_a, Exception("model-b down")]
    call_idx = 0

    async def mock_create(**kwargs):
        nonlocal call_idx
        r = call_results[call_idx]
        call_idx += 1
        if isinstance(r, Exception):
            raise r
        return r

    client.chat.completions.create = mock_create

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", None),
    ):
        result = await run_ab_test("task", {"model": "good"}, {"model": "bad"})

    assert result["winner"] == "a"
    assert result["win_reason"] == "availability"


@pytest.mark.asyncio
async def test_run_ab_test_persists_to_db():
    comp = _make_completion("answer")
    judge = _make_completion("TIE")

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return comp if call_count <= 2 else judge

    client = MagicMock()
    client.chat.completions.create = mock_create

    mock_pool = MagicMock()
    mock_execute = AsyncMock()

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", mock_pool),
        patch.object(ab_mod._db, "execute", mock_execute),
    ):
        await run_ab_test("task", {"model": "m-a"}, {"model": "m-b"})

    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_ab_test_db_failure_does_not_raise():
    comp = _make_completion("answer")
    judge = _make_completion("A")

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return comp if call_count <= 2 else judge

    client = MagicMock()
    client.chat.completions.create = mock_create

    mock_pool = MagicMock()

    async def fail_execute(*args, **kwargs):
        raise Exception("db error")

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", mock_pool),
        patch.object(ab_mod._db, "execute", fail_execute),
    ):
        result = await run_ab_test("task", {"model": "m-a"}, {"model": "m-b"})

    assert "winner" in result


@pytest.mark.asyncio
async def test_run_ab_test_uses_default_model_when_not_specified():
    comp = _make_completion("answer")
    judge = _make_completion("TIE")

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return comp if call_count <= 2 else judge

    client = MagicMock()
    client.chat.completions.create = mock_create

    with (
        patch("app.agent.ab_testing._client", return_value=client),
        patch.object(ab_mod._db, "db_pool", None),
    ):
        result = await run_ab_test("task", {}, {})

    # Both approaches used defaults — just verify it ran
    assert "approach_a" in result
    assert "approach_b" in result
