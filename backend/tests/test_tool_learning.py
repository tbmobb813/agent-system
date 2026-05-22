"""Tests for app/agent/tool_learning.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agent.tool_learning as tl_mod
from app.agent.tool_learning import get_tool_hint, learn_tool_chains

# ── learn_tool_chains ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_learn_tool_chains_skips_when_no_pool():
    with patch.object(tl_mod._db, "db_pool", None):
        await learn_tool_chains()  # should return silently


@pytest.mark.asyncio
async def test_learn_tool_chains_skips_on_db_error():
    mock_pool = MagicMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(side_effect=Exception("db down"))),
    ):
        await learn_tool_chains()  # should not raise


@pytest.mark.asyncio
async def test_learn_tool_chains_skips_task_types_below_min_sample():
    mock_pool = MagicMock()
    rows = [
        {"query": "write some code", "status": "completed", "tool_name": "code_runner"},
        {"query": "write some code", "status": "completed", "tool_name": "web_search"},
    ]
    mock_execute = AsyncMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", mock_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
    ):
        await learn_tool_chains()
    mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_learn_tool_chains_upserts_when_enough_samples():
    mock_pool = MagicMock()
    rows = []
    for i in range(6):
        rows.append(
            {
                "query": f"write code task {i}",
                "status": "completed",
                "tool_name": "code_runner",
            }
        )
        rows.append(
            {
                "query": f"write code task {i}",
                "status": "completed",
                "tool_name": "web_search",
            }
        )

    mock_execute = AsyncMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", mock_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
    ):
        await learn_tool_chains()
    mock_execute.assert_awaited()


@pytest.mark.asyncio
async def test_learn_tool_chains_upsert_failure_does_not_raise():
    mock_pool = MagicMock()
    rows = [
        {"query": f"code task {i}", "status": "completed", "tool_name": "tool_x"}
        for i in range(6)
    ]

    async def fail_execute(*a, **kw):
        raise Exception("upsert failed")

    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", fail_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
    ):
        await learn_tool_chains()  # should not raise


@pytest.mark.asyncio
async def test_learn_tool_chains_success_rate_all_completed():
    """All completed tasks → success_rate == 1.0"""
    mock_pool = MagicMock()
    rows = [
        {"query": f"write code {i}", "status": "completed", "tool_name": "code_runner"}
        for i in range(6)
    ]
    captured: list = []

    async def capture_execute(sql, *args):
        captured.append(args)

    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", capture_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
    ):
        await learn_tool_chains()

    assert len(captured) == 1
    # args order: task_type, recommended_sequence, success_rate, sample_count
    assert captured[0][2] == 1.0


@pytest.mark.asyncio
async def test_learn_tool_chains_success_rate_mixed():
    """4 completed + 2 failed → success_rate == 0.667"""
    mock_pool = MagicMock()
    rows = [
        {"query": f"write code {i}", "status": "completed", "tool_name": "code_runner"}
        for i in range(4)
    ] + [
        {"query": f"write code bad {i}", "status": "failed", "tool_name": "code_runner"}
        for i in range(2)
    ]
    captured: list = []

    async def capture_execute(sql, *args):
        captured.append(args)

    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", capture_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
    ):
        await learn_tool_chains()

    assert len(captured) == 1
    success_rate = captured[0][2]
    assert abs(success_rate - round(4 / 6, 3)) < 0.001


@pytest.mark.asyncio
async def test_learn_tool_chains_success_rate_all_failed():
    """All failed tasks → success_rate == 0.0"""
    mock_pool = MagicMock()
    rows = [
        {"query": f"write code {i}", "status": "failed", "tool_name": "code_runner"}
        for i in range(6)
    ]
    captured: list = []

    async def capture_execute(sql, *args):
        captured.append(args)

    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch.object(tl_mod._db, "fetch", AsyncMock(return_value=rows)),
        patch.object(tl_mod._db, "execute", capture_execute),
        patch("app.agent.tool_learning.MIN_SAMPLE_SIZE", 5),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
    ):
        await learn_tool_chains()

    assert len(captured) == 1
    assert captured[0][2] == 0.0


# ── get_tool_hint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tool_hint_returns_empty_when_no_pool():
    with patch.object(tl_mod._db, "db_pool", None):
        result = await get_tool_hint("write some Python code")
    assert result == ""


@pytest.mark.asyncio
async def test_get_tool_hint_returns_empty_for_general_query():
    mock_pool = MagicMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch("app.agent.tool_learning.classify_query", return_value="general"),
    ):
        result = await get_tool_hint("hello how are you")
    assert result == ""


@pytest.mark.asyncio
async def test_get_tool_hint_returns_empty_on_db_error():
    mock_pool = MagicMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
        patch.object(
            tl_mod._db, "fetchrow", AsyncMock(side_effect=Exception("timeout"))
        ),
    ):
        result = await get_tool_hint("write code")
    assert result == ""


@pytest.mark.asyncio
async def test_get_tool_hint_returns_empty_when_no_row():
    mock_pool = MagicMock()
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
        patch.object(tl_mod._db, "fetchrow", AsyncMock(return_value=None)),
    ):
        result = await get_tool_hint("write code")
    assert result == ""


@pytest.mark.asyncio
async def test_get_tool_hint_returns_empty_when_no_tools_in_row():
    import json

    mock_pool = MagicMock()
    row = {"recommended_sequence": json.dumps([]), "sample_count": 10}
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
        patch.object(tl_mod._db, "fetchrow", AsyncMock(return_value=row)),
    ):
        result = await get_tool_hint("write code")
    assert result == ""


@pytest.mark.asyncio
async def test_get_tool_hint_returns_hint_string():
    import json

    mock_pool = MagicMock()
    row = {
        "recommended_sequence": json.dumps(["code_runner", "web_search"]),
        "sample_count": 12,
    }
    with (
        patch.object(tl_mod._db, "db_pool", mock_pool),
        patch("app.agent.tool_learning.classify_query", return_value="coding"),
        patch.object(tl_mod._db, "fetchrow", AsyncMock(return_value=row)),
    ):
        result = await get_tool_hint("write some code please")
    assert "coding" in result
    assert "code_runner" in result
    assert "12" in result
