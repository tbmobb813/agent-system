"""Tests for configuration module."""

import pytest
from unittest.mock import AsyncMock
from app.config import Settings, CostTracker


def test_settings_initialization():
    """Test Settings initializes with defaults."""
    settings = Settings()
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is False
    assert settings.OPENROUTER_BUDGET_MONTHLY == 30.0
    assert "localhost" in settings.ALLOWED_HOSTS


def test_settings_cors_defaults():
    """Test CORS settings have proper defaults."""
    settings = Settings()
    assert len(settings.CORS_ORIGINS) > 0
    assert any("localhost" in origin for origin in settings.CORS_ORIGINS)


def test_settings_model_defaults():
    """Test model routing settings are set."""
    settings = Settings()
    assert settings.DEFAULT_MODEL_SIMPLE
    assert settings.DEFAULT_MODEL_CODING
    assert settings.DEFAULT_MODEL_AGENT
    assert "deepseek" in settings.DEFAULT_MODEL_SIMPLE
    assert (
        "claude" in settings.DEFAULT_MODEL_AGENT
        or "claude" in settings.DEFAULT_MODEL_ADVANCED
    )


def test_cost_tracker_initialization():
    """Test CostTracker initializes correctly."""
    tracker = CostTracker()
    assert tracker.db_pool is None
    assert tracker._spent_cache == 0.0
    assert tracker._call_info == {}
    assert len(tracker.MODEL_PRICING) > 0


def test_cost_tracker_model_pricing():
    """Test CostTracker has pricing for all default models."""
    tracker = CostTracker()
    assert "deepseek/deepseek-chat" in tracker.MODEL_PRICING
    assert "anthropic/claude-3.5-haiku" in tracker.MODEL_PRICING
    assert tracker.MODEL_PRICING["deepseek/deepseek-chat"]["input"] == 0.14


@pytest.mark.asyncio
async def test_cost_tracker_close_no_pool():
    """Test CostTracker close with no pool."""
    tracker = CostTracker()
    await tracker.close()  # Should not raise


@pytest.mark.asyncio
async def test_cost_tracker_initialize_success(monkeypatch):
    """Test CostTracker initializes a pool successfully."""
    tracker = CostTracker()
    mock_pool = AsyncMock()

    async def _create_pool(*args, **kwargs):
        return mock_pool

    monkeypatch.setattr("app.config.asyncpg.create_pool", _create_pool)
    await tracker.initialize("postgresql://user:pass@localhost/db")

    assert tracker.db_pool is mock_pool


@pytest.mark.asyncio
async def test_cost_tracker_fallback_helpers_without_pool():
    """Test helper fallbacks when no database pool exists."""
    tracker = CostTracker()

    assert await tracker.get_spent_month() == 0.0
    assert await tracker.get_spent_today_date() == 0.0
    assert await tracker.get_spent_by_model() == {}
    assert tracker.pop_call_info("missing") == {
        "cost": 0.0,
        "model": None,
        "usage": None,
    }
    assert tracker._pop_call_info("missing") == {
        "cost": 0.0,
        "model": None,
        "usage": None,
    }
    assert await tracker.get_last_call_cost() == 0.0
    assert tracker.get_last_model() is None
    assert tracker.get_last_usage() is None
    assert tracker.get_model_pricing("unknown-model") == {
        "input": 3.0,
        "output": 15.0,
    }


def test_settings_budget_defaults():
    """Test budget-related settings."""
    settings = Settings()
    assert settings.OPENROUTER_BUDGET_MONTHLY == 30.0
    assert settings.BUDGET_ALERT_PERCENT_80 is True
    assert settings.BUDGET_ALERT_PERCENT_95 is True
