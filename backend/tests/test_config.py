"""Tests for configuration module."""

import pytest
from unittest.mock import AsyncMock, patch
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
    assert "claude" in settings.DEFAULT_MODEL_AGENT or "claude" in settings.DEFAULT_MODEL_ADVANCED


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


def test_settings_budget_defaults():
    """Test budget-related settings."""
    settings = Settings()
    assert settings.OPENROUTER_BUDGET_MONTHLY == 30.0
    assert settings.BUDGET_ALERT_PERCENT_80 is True
    assert settings.BUDGET_ALERT_PERCENT_95 is True
