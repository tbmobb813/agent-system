"""Tests for app/agent/quality.py — sampled response-quality scorer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agent.quality as quality_mod
from app.agent.quality import (
    _extract_json_object,
    _should_sample,
    score_response_quality,
)

# ── _extract_json_object ──────────────────────────────────────────────────────


def test_extract_json_object_valid():
    data = _extract_json_object('{"helpfulness": 4, "overall_score": 3}')
    assert data == {"helpfulness": 4, "overall_score": 3}


def test_extract_json_object_embedded():
    data = _extract_json_object('some text {"key": "val"} trailing')
    assert data == {"key": "val"}


def test_extract_json_object_empty_string():
    assert _extract_json_object("") is None


def test_extract_json_object_whitespace():
    assert _extract_json_object("   ") is None


def test_extract_json_object_no_braces():
    assert _extract_json_object("just plain text") is None


def test_extract_json_object_malformed():
    assert _extract_json_object("{broken json") is None


def test_extract_json_object_returns_none_for_list():
    # top-level list is not a dict
    assert _extract_json_object("[1, 2, 3]") is None


def test_extract_json_object_nested_braces():
    data = _extract_json_object('{"a": {"b": 1}}')
    assert data == {"a": {"b": 1}}


# ── _should_sample ────────────────────────────────────────────────────────────


def test_should_sample_disabled_by_setting():
    with patch.object(quality_mod.settings, "QUALITY_SCORING_ENABLED", False):
        assert _should_sample() is False


def test_should_sample_no_api_key():
    with (
        patch.object(quality_mod.settings, "QUALITY_SCORING_ENABLED", True),
        patch.object(quality_mod.settings, "OPENROUTER_API_KEY", ""),
    ):
        assert _should_sample() is False


def test_should_sample_rate_zero():
    with (
        patch.object(quality_mod.settings, "QUALITY_SCORING_ENABLED", True),
        patch.object(quality_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch.object(quality_mod.settings, "QUALITY_SCORING_SAMPLE_RATE", 0.0),
        patch("app.agent.quality.random.random", return_value=0.5),
    ):
        assert _should_sample() is False


def test_should_sample_rate_one():
    with (
        patch.object(quality_mod.settings, "QUALITY_SCORING_ENABLED", True),
        patch.object(quality_mod.settings, "OPENROUTER_API_KEY", "sk-test"),
        patch.object(quality_mod.settings, "QUALITY_SCORING_SAMPLE_RATE", 1.0),
        patch("app.agent.quality.random.random", return_value=0.99),
    ):
        assert _should_sample() is True


# ── _quality_table_available ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quality_table_available_no_pool():
    quality_mod._response_quality_table_exists = None
    with patch.object(quality_mod._db, "db_pool", None):
        result = await quality_mod._quality_table_available()
    assert result is False
    quality_mod._response_quality_table_exists = None  # reset


@pytest.mark.asyncio
async def test_quality_table_available_cached_true():
    quality_mod._response_quality_table_exists = True
    result = await quality_mod._quality_table_available()
    assert result is True
    quality_mod._response_quality_table_exists = None


@pytest.mark.asyncio
async def test_quality_table_available_cached_false():
    quality_mod._response_quality_table_exists = False
    result = await quality_mod._quality_table_available()
    assert result is False
    quality_mod._response_quality_table_exists = None


@pytest.mark.asyncio
async def test_quality_table_available_fetchval_true():
    quality_mod._response_quality_table_exists = None
    fake_pool = MagicMock()
    with (
        patch.object(quality_mod._db, "db_pool", fake_pool),
        patch("app.agent.quality.fetchval", new=AsyncMock(return_value=True)),
    ):
        result = await quality_mod._quality_table_available()
    assert result is True
    quality_mod._response_quality_table_exists = None


@pytest.mark.asyncio
async def test_quality_table_available_fetchval_exception():
    quality_mod._response_quality_table_exists = None
    fake_pool = MagicMock()
    with (
        patch.object(quality_mod._db, "db_pool", fake_pool),
        patch(
            "app.agent.quality.fetchval",
            new=AsyncMock(side_effect=Exception("db down")),
        ),
    ):
        result = await quality_mod._quality_table_available()
    assert result is False
    quality_mod._response_quality_table_exists = None


# ── score_response_quality ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_response_quality_skips_when_not_sampled():
    with patch("app.agent.quality._should_sample", return_value=False):
        # Should return immediately without hitting judge
        await score_response_quality(
            query="hello", response="world", task_id="t1", user_id="u1", model_used="m1"
        )


@pytest.mark.asyncio
async def test_score_response_quality_skips_empty_response():
    with patch("app.agent.quality._should_sample", return_value=True):
        await score_response_quality(
            query="hello", response="   ", task_id="t1", user_id="u1", model_used="m1"
        )


@pytest.mark.asyncio
async def test_score_response_quality_skips_when_table_unavailable():
    with (
        patch("app.agent.quality._should_sample", return_value=True),
        patch(
            "app.agent.quality._quality_table_available",
            new=AsyncMock(return_value=False),
        ),
    ):
        await score_response_quality(
            query="q", response="r", task_id=None, user_id=None, model_used=None
        )


@pytest.mark.asyncio
async def test_score_response_quality_happy_path():
    judge_response = json.dumps(
        {
            "helpfulness": 4,
            "accuracy": 5,
            "conciseness": 3,
            "tool_usage_appropriateness": 4,
            "overall_score": 4,
            "rationale": "Good answer",
        }
    )

    mock_choice = MagicMock()
    mock_choice.message.content = judge_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with (
        patch("app.agent.quality._should_sample", return_value=True),
        patch(
            "app.agent.quality._quality_table_available",
            new=AsyncMock(return_value=True),
        ),
        patch("app.agent.quality._judge_client", return_value=mock_client),
        patch("app.agent.quality.execute", new=AsyncMock()) as mock_exec,
    ):
        await score_response_quality(
            query="What is 2+2?",
            response="The answer is 4.",
            task_id="task-1",
            user_id="user-1",
            model_used="gpt-4",
        )
        mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_score_response_quality_clamps_out_of_range_scores():
    judge_response = json.dumps(
        {
            "helpfulness": 10,
            "accuracy": 0,
            "conciseness": 6,
            "tool_usage_appropriateness": -1,
            "overall_score": 99,
            "rationale": "x" * 300,
        }
    )

    mock_choice = MagicMock()
    mock_choice.message.content = judge_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    captured = {}

    async def capture_execute(sql, *args):
        captured["args"] = args

    with (
        patch("app.agent.quality._should_sample", return_value=True),
        patch(
            "app.agent.quality._quality_table_available",
            new=AsyncMock(return_value=True),
        ),
        patch("app.agent.quality._judge_client", return_value=mock_client),
        patch("app.agent.quality.execute", side_effect=capture_execute),
    ):
        await score_response_quality(
            query="q", response="r", task_id=None, user_id=None, model_used=None
        )

    args = captured["args"]
    helpfulness, accuracy, conciseness, tool_usage, overall = (
        args[3],
        args[4],
        args[5],
        args[6],
        args[7],
    )
    assert 1 <= helpfulness <= 5
    assert 1 <= accuracy <= 5
    assert 1 <= conciseness <= 5
    assert 1 <= tool_usage <= 5
    assert 1 <= overall <= 5


@pytest.mark.asyncio
async def test_score_response_quality_non_json_response():
    mock_choice = MagicMock()
    mock_choice.message.content = "Sorry, I cannot score this."
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with (
        patch("app.agent.quality._should_sample", return_value=True),
        patch(
            "app.agent.quality._quality_table_available",
            new=AsyncMock(return_value=True),
        ),
        patch("app.agent.quality._judge_client", return_value=mock_client),
        patch("app.agent.quality.execute", new=AsyncMock()) as mock_exec,
    ):
        await score_response_quality(
            query="q", response="r", task_id=None, user_id=None, model_used=None
        )
        mock_exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_score_response_quality_api_exception_is_swallowed():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("network error")
    )

    with (
        patch("app.agent.quality._should_sample", return_value=True),
        patch(
            "app.agent.quality._quality_table_available",
            new=AsyncMock(return_value=True),
        ),
        patch("app.agent.quality._judge_client", return_value=mock_client),
    ):
        # Should not raise
        await score_response_quality(
            query="q", response="r", task_id=None, user_id=None, model_used=None
        )
