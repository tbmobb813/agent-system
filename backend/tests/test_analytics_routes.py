"""Analytics API routes — DB calls mocked."""

from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.cost_learning import EfficiencyScore
from app.main import app

AUTH = {"Authorization": "Bearer sk-agent-local-dev"}


async def test_analytics_overview(monkeypatch):
    async def fetchval_ov(*_a, **_k):
        return 5.0

    monkeypatch.setattr(
        "app.routes.analytics.fetchval", AsyncMock(side_effect=fetchval_ov)
    )

    async def _fetch_forbidden(*_a, **_k):
        raise AssertionError("fetch should not run for overview")

    monkeypatch.setattr(
        "app.routes.analytics.fetch", AsyncMock(side_effect=_fetch_forbidden)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/overview", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["budget"] >= 0
    assert body["spent_month"] == pytest.approx(5.0)
    assert body["spent_today"] == pytest.approx(5.0)


async def test_analytics_overview_503_when_db_raises(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.fetchval",
        AsyncMock(side_effect=RuntimeError("no pool")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/overview", headers=AUTH)
    assert r.status_code == 503


@pytest.mark.parametrize(
    ("path", "checker"),
    [
        (
            "/analytics/daily",
            lambda b: "points" in b and b["days"] >= 1,
        ),
        (
            "/analytics/models",
            lambda b: any(m.get("model") == "x/y" for m in b["metrics"]),
        ),
        (
            "/analytics/tools",
            lambda b: (
                b["tools"] and b["tools"][0]["tool_name"] and b["tools"][0]["uses"] >= 1
            ),
        ),
        (
            "/analytics/decisions",
            lambda b: b["decisions"] and "decision_point" in b["decisions"][0],
        ),
        (
            "/analytics/errors",
            lambda b: b["patterns"][0]["error_type"] == "timeout",
        ),
    ],
)
async def test_analytics_list_routes(monkeypatch, path, checker):
    async def fv(*_a, **_k):
        return 100.0

    def _dispatch_sql(query: str, *_args, **_kwargs):
        ql = query.lower()

        if "budget_alerts" in ql:
            return []
        if "generate_series" in ql:
            return [{"day": date(2026, 1, 10), "total_cost": 0.1, "calls": 1}]
        if "from tool_calls tc" in ql and "tool_task_cost" in ql.replace("\n", " "):
            return [
                {
                    "tool_name": "x",
                    "uses": 1,
                    "unique_tasks": 1,
                    "total_task_cost": 0.1,
                },
            ]
        if "group by coalesce(model_used" in ql or (
            "from tasks" in ql and "group by" in ql and "model" in ql
        ):
            return [
                {
                    "model": "x/y",
                    "tasks": 4,
                    "successful": 2,
                    "avg_execution_time": 1.5,
                    "avg_cost": 0.001,
                    "total_cost": 0.004,
                }
            ]
        if "from decisions" in ql:
            return [
                {
                    "decision_point": "tool_selection",
                    "chosen": "x",
                    "times_chosen": 2,
                    "avg_confidence": 0.7,
                    "successes": 1,
                    "failures": 0,
                }
            ]
        if "from error_patterns" in ql:
            return [
                {
                    "error_type": "timeout",
                    "recovery_strategy": "retry",
                    "model_used": "m",
                    "occurrences": 3,
                    "recovered": 1,
                }
            ]

        raise AssertionError(f"unhandled analytics query: {ql[:100]}")

    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(side_effect=fv))
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=lambda q, *a, **k: _dispatch_sql(q)),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(path + "?days=7", headers=AUTH)
    assert r.status_code == 200
    assert checker(r.json())


async def test_analytics_tools_schema_error_returns_empty_tools(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(return_value=50.0))

    calls = []

    async def flaky_fetch(query: str, *_a, **_k):
        ql = query.lower()
        calls.append(True)
        if "tool_calls" in ql.replace("\n", " "):
            raise ValueError("no such table tool_calls")
        if "budget_alerts" in ql:
            return []
        if "generate_series" in ql:
            return [{"day": date.today(), "total_cost": 1.0, "calls": 1}]
        if "decisions" in ql:
            return []
        if "error_patterns" in ql:
            return []
        raise AssertionError("unexpected")

    monkeypatch.setattr(
        "app.routes.analytics.fetch", AsyncMock(side_effect=flaky_fetch)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/tools?days=5", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["tools"] == []


async def test_analytics_tools_runtime_error_returns_503(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.routes.analytics.fetch", AsyncMock(side_effect=boom))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/tools?days=5", headers=AUTH)

    assert r.status_code == 503


async def test_analytics_alerts_risk_high(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(return_value=999.0))

    async def fx(query: str, *_a, **_k):
        if "budget_alerts" in query.lower():
            return []
        raise AssertionError("unexpected fetch in alerts")

    monkeypatch.setattr("app.routes.analytics.fetch", AsyncMock(side_effect=fx))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/alerts?days=7", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert body["risk_level"] == "high"


async def test_analytics_skills_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.get_agent_profile",
        AsyncMock(return_value={"skills": [], "growth_areas": []}),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/skills", headers=AUTH)
    assert r.status_code == 200


async def test_analytics_cost_efficiency_empty(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.get_efficiency_scores", lambda: {})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/cost-efficiency", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["models"] == []


async def test_analytics_cost_efficiency_ranked(monkeypatch):
    t = datetime.utcnow()
    scores = {
        "a": EfficiencyScore(
            model="a",
            avg_cost=0.01,
            thumbs_up_rate=0.9,
            efficiency=90,
            sample_count=9,
            last_updated=t,
        ),
        "b": EfficiencyScore(
            model="b",
            avg_cost=0.02,
            thumbs_up_rate=0.5,
            efficiency=40,
            sample_count=8,
            last_updated=t,
        ),
    }
    monkeypatch.setattr("app.routes.analytics.get_efficiency_scores", lambda: scores)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/cost-efficiency", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert body["models"][0]["model"] == "a"


async def test_analytics_ab_tests_empty_on_fetch_error(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("db")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/ab-tests?limit=3", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["tests"] == []


async def test_analytics_ab_tests_rows(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(
            return_value=[
                {
                    "task_description": "task",
                    "approach_a": '{"model":"m"}',
                    "approach_b": "{}",
                    "result_a": '{"cost": 1}',
                    "result_b": '{"cost": 2}',
                    "winner": "a",
                    "win_reason": "cheaper",
                    "created_at": datetime(2026, 1, 1, 12, 0, 0),
                }
            ]
        ),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/ab-tests", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert len(body["tests"]) == 1
    assert body["tests"][0]["winner"] == "a"


async def test_analytics_ab_test_run_validation(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.run_ab_test",
        AsyncMock(side_effect=AssertionError("must not call")),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/analytics/ab-tests/run",
            headers=AUTH,
            params={
                "task": " ",
                "model_a": "a",
                "model_b": "b",
                "system_prompt_a": "",
                "system_prompt_b": "",
            },
        )

    assert r.status_code == 400


async def test_analytics_ab_test_run(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.run_ab_test",
        AsyncMock(return_value={"winner": "a", "win_reason": "ok", "task_id": "t1"}),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/analytics/ab-tests/run",
            headers=AUTH,
            params={
                "task": "compare",
                "model_a": "m1",
                "model_b": "m2",
                "system_prompt_a": "",
                "system_prompt_b": "",
            },
        )

    assert r.status_code == 200
    assert r.json()["winner"] == "a"


async def test_decisions_fetch_failure_returns_empty(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(return_value=30.0))
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("missing table")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/decisions", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["decisions"] == []


async def test_analytics_daily_503(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(return_value=1.0))
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/daily?days=7", headers=AUTH)
    assert r.status_code == 503


async def test_analytics_models_503(monkeypatch):
    monkeypatch.setattr("app.routes.analytics.fetchval", AsyncMock(return_value=1.0))
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/models?days=14", headers=AUTH)
    assert r.status_code == 503


async def test_analytics_errors_empty_on_fetch_exc(monkeypatch):
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("no table")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/errors", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["patterns"] == []


async def test_analytics_alerts_medium_risk(monkeypatch):
    async def _overview(**_kwargs):
        return {
            "budget": 100.0,
            "spent_month": 70.0,
            "spent_today": 2.0,
            "remaining": 30.0,
            "daily_average": 2.5,
            "projected_total": 92.5,
            "percent_used": 70.0,
            "days_elapsed": 10,
            "days_in_month": 30,
            "is_overspend_risk": False,
        }

    monkeypatch.setattr("app.routes.analytics.get_analytics_overview", _overview)
    monkeypatch.setattr(
        "app.routes.analytics.fetch",
        AsyncMock(side_effect=RuntimeError("alerts table missing")),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/analytics/alerts?days=7", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert body["risk_level"] == "medium"
    assert body["alerts"] == []
