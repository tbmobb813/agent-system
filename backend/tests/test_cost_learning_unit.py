"""Cost-efficiency cache helpers."""

from datetime import UTC, datetime, timedelta

import pytest

import app.agent.cost_learning as cl


@pytest.fixture(autouse=True)
def _reset_efficiency_cache():
    cl._cache.clear()
    prev = cl._last_refresh
    cl._last_refresh = None
    yield
    cl._cache.clear()
    cl._last_refresh = prev


@pytest.mark.asyncio
async def test_refresh_skips_without_db(monkeypatch):
    monkeypatch.setattr(cl._db, "db_pool", None)
    await cl.refresh_efficiency_cache()


@pytest.mark.asyncio
async def test_refresh_throttled(monkeypatch):
    monkeypatch.setattr(cl._db, "db_pool", object())
    cl._last_refresh = datetime.now(UTC)
    called = []

    async def _fetch(*_a, **_k):
        called.append(True)
        return []

    monkeypatch.setattr(cl._db, "fetch", _fetch)
    await cl.refresh_efficiency_cache()
    assert called == []


@pytest.mark.asyncio
async def test_refresh_populates_cache(monkeypatch):
    monkeypatch.setattr(cl._db, "db_pool", object())
    cl._cache.clear()
    cl._last_refresh = datetime.now(UTC) - timedelta(hours=2)

    async def _fetch(*_a, **_k):
        return [
            {
                "model": "m1",
                "total_tasks": 10,
                "avg_cost": 0.01,
                "feedback_count": 2,
                "thumbs_up": 1,
            }
        ]

    monkeypatch.setattr(cl._db, "fetch", _fetch)
    await cl.refresh_efficiency_cache()
    assert "m1" in cl.get_efficiency_scores()


def test_suggest_model_insufficient_cache():
    cl._cache.clear()
    assert cl.suggest_model("any", ["alt"]) == "any"


def test_suggest_model_prefers_efficient_alt():
    cl._cache.clear()
    cl._cache["m1"] = cl.EfficiencyScore(
        model="m1",
        avg_cost=0.05,
        thumbs_up_rate=0.9,
        sample_count=20,
        efficiency=10.0,
    )
    cl._cache["m2"] = cl.EfficiencyScore(
        model="m2",
        avg_cost=0.01,
        thumbs_up_rate=0.95,
        sample_count=20,
        efficiency=250.0,
    )
    assert cl.suggest_model("m1", ["m2"]) == "m2"
