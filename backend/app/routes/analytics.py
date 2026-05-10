"""
Analytics routes for cost, performance, and tool usage insights.
"""

import json
from calendar import monthrange
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.database import fetch, fetchval, execute
from app.utils.auth import verify_api_key
from app.agent.skill_registry import get_agent_profile
from app.agent.cost_learning import get_efficiency_scores
from app.agent.ab_testing import run_ab_test

router = APIRouter(prefix="/analytics", tags=["analytics"])


class SkillUpsertRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=120)
    skill_name: str = Field(min_length=1, max_length=160)
    success_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    total_uses: int = Field(default=1, ge=0)
    proficiency_level: str = Field(default="competent")
    required_tools: list[str] = Field(default_factory=list)


def _projected_month_total(spent_month: float) -> float:
    now = datetime.utcnow()
    days_in_month = monthrange(now.year, now.month)[1]
    # Include current day as elapsed to avoid division by zero on the 1st.
    days_elapsed = max(now.day, 1)
    daily_avg = spent_month / days_elapsed
    return daily_avg * days_in_month


@router.get("/overview")
async def get_analytics_overview(api_key: str = Depends(verify_api_key)):
    """Budget KPIs and month-end projection."""
    try:
        spent_month_raw = await fetchval(
            """
            SELECT COALESCE(SUM(cost), 0)
            FROM cost_tracking
            WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
            """
        )
        spent_today_raw = await fetchval(
            """
            SELECT COALESCE(SUM(cost), 0)
            FROM cost_tracking
            WHERE DATE(created_at) = CURRENT_DATE
            """
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")

    spent_month = float(spent_month_raw or 0.0)
    spent_today = float(spent_today_raw or 0.0)
    budget = float(settings.OPENROUTER_BUDGET_MONTHLY)
    remaining = max(0.0, budget - spent_month)

    now = datetime.utcnow()
    days_in_month = monthrange(now.year, now.month)[1]
    days_elapsed = max(now.day, 1)
    daily_avg = spent_month / days_elapsed
    projected_total = _projected_month_total(spent_month)

    return {
        "budget": budget,
        "spent_month": spent_month,
        "spent_today": spent_today,
        "remaining": remaining,
        "daily_average": daily_avg,
        "projected_total": projected_total,
        "percent_used": (spent_month / budget) * 100 if budget > 0 else 0,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "is_overspend_risk": projected_total > budget,
    }


@router.get("/daily")
async def get_analytics_daily(days: int = 7, api_key: str = Depends(verify_api_key)):
    """Daily cost trend for the last N days."""
    safe_days = min(max(days, 1), 60)
    try:
        rows = await fetch(
            """
            WITH date_series AS (
                SELECT generate_series(
                    CURRENT_DATE - ($1::int - 1),
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date AS day
            ),
            costs AS (
                SELECT DATE(created_at) AS day,
                       COALESCE(SUM(cost), 0) AS total_cost,
                       COUNT(*) AS calls
                FROM cost_tracking
                WHERE DATE(created_at) >= CURRENT_DATE - ($1::int - 1)
                GROUP BY DATE(created_at)
            )
            SELECT ds.day,
                   COALESCE(c.total_cost, 0) AS total_cost,
                   COALESCE(c.calls, 0) AS calls
            FROM date_series ds
            LEFT JOIN costs c ON c.day = ds.day
            ORDER BY ds.day ASC
            """,
            safe_days,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")

    points = [
        {
            "date": r["day"].isoformat(),
            "cost": float(r["total_cost"] or 0.0),
            "calls": int(r["calls"] or 0),
        }
        for r in rows
    ]
    return {"days": safe_days, "points": points}


@router.get("/models")
async def get_analytics_models(days: int = 30, api_key: str = Depends(verify_api_key)):
    """Task performance grouped by model."""
    safe_days = min(max(days, 1), 180)
    try:
        rows = await fetch(
            """
            SELECT
                COALESCE(model_used, 'unknown') AS model,
                COUNT(*) AS tasks,
                COUNT(*) FILTER (WHERE status = 'completed') AS successful,
                AVG(COALESCE(execution_time, 0)) AS avg_execution_time,
                AVG(COALESCE(cost, 0)) AS avg_cost,
                SUM(COALESCE(cost, 0)) AS total_cost
            FROM tasks
            WHERE created_at >= NOW() - ($1::int * INTERVAL '1 day')
            GROUP BY COALESCE(model_used, 'unknown')
            ORDER BY total_cost DESC
            """,
            safe_days,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")

    metrics = []
    for r in rows:
        tasks = int(r["tasks"] or 0)
        successful = int(r["successful"] or 0)
        success_rate = (successful / tasks) * 100 if tasks > 0 else 0
        metrics.append(
            {
                "model": r["model"],
                "tasks": tasks,
                "successful": successful,
                "success_rate": round(success_rate, 2),
                "avg_execution_time": float(r["avg_execution_time"] or 0.0),
                "avg_cost": float(r["avg_cost"] or 0.0),
                "total_cost": float(r["total_cost"] or 0.0),
            }
        )
    return {"days": safe_days, "metrics": metrics}


@router.get("/tools")
async def get_analytics_tools(days: int = 30, api_key: str = Depends(verify_api_key)):
    """Tool usage and associated task cost, when available."""
    safe_days = min(max(days, 1), 180)
    try:
        rows = await fetch(
            """
            WITH tool_task_cost AS (
                SELECT
                    tc.tool_name,
                    tc.task_id,
                    MAX(COALESCE(t.cost, 0)) AS task_cost
                FROM tool_calls tc
                LEFT JOIN tasks t ON t.id::text = tc.task_id
                WHERE tc.created_at >= NOW() - ($1::int * INTERVAL '1 day')
                GROUP BY tc.tool_name, tc.task_id
            )
            SELECT
                tool_name,
                COUNT(*) AS uses,
                COUNT(DISTINCT task_id) AS unique_tasks,
                SUM(task_cost) AS total_task_cost
            FROM tool_task_cost
            GROUP BY tool_name
            ORDER BY uses DESC
            """,
            safe_days,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")
    except Exception:
        # tool_calls may not exist in older environments.
        return {"days": safe_days, "tools": []}

    tools = [
        {
            "tool_name": r["tool_name"],
            "uses": int(r["uses"] or 0),
            "unique_tasks": int(r["unique_tasks"] or 0),
            "total_task_cost": float(r["total_task_cost"] or 0.0),
        }
        for r in rows
    ]
    return {"days": safe_days, "tools": tools}


@router.get("/alerts")
async def get_budget_alerts(days: int = 30, api_key: str = Depends(verify_api_key)):
    """Budget risk signal plus recent generated alert records."""
    safe_days = min(max(days, 1), 365)
    overview = await get_analytics_overview(api_key=api_key)

    try:
        rows = await fetch(
            """
            SELECT alert_type, alert_message, spent, budget, created_at, acknowledged
            FROM budget_alerts
            WHERE created_at >= NOW() - ($1::int * INTERVAL '1 day')
            ORDER BY created_at DESC
            LIMIT 50
            """,
            safe_days,
        )
    except Exception:
        rows = []

    projected_total = float(overview["projected_total"])
    budget = float(overview["budget"])
    risk_level = "ok"
    if projected_total > budget:
        risk_level = "high"
    elif projected_total > budget * 0.9:
        risk_level = "medium"

    alerts = [
        {
            "type": r["alert_type"],
            "message": r["alert_message"],
            "spent": float(r["spent"] or 0.0),
            "budget": float(r["budget"] or 0.0),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "acknowledged": bool(r["acknowledged"]),
        }
        for r in rows
    ]

    return {
        "days": safe_days,
        "risk_level": risk_level,
        "projected_total": projected_total,
        "budget": budget,
        "delta": projected_total - budget,
        "alerts": alerts,
    }


@router.get("/skills")
async def get_skills_profile(api_key: str = Depends(verify_api_key)):
    """Agent skill profile: competency levels and growth areas by task type."""
    return await get_agent_profile()


@router.post("/skills")
async def upsert_skill_profile(
    body: SkillUpsertRequest,
    api_key: str = Depends(verify_api_key),
):
    """Create/update a skill profile entry manually."""
    try:
        await execute(
            """
            INSERT INTO skills (task_type, skill_name, success_rate, total_uses, proficiency_level, required_tools, last_computed)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
            ON CONFLICT (task_type)
            DO UPDATE SET
                skill_name = EXCLUDED.skill_name,
                success_rate = EXCLUDED.success_rate,
                total_uses = EXCLUDED.total_uses,
                proficiency_level = EXCLUDED.proficiency_level,
                required_tools = EXCLUDED.required_tools,
                last_computed = NOW()
            """,
            body.task_type.strip(),
            body.skill_name.strip(),
            float(body.success_rate),
            int(body.total_uses),
            body.proficiency_level.strip() or "competent",
            json.dumps(body.required_tools),
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upsert skill: {e}")

    return {"status": "upserted", "task_type": body.task_type.strip()}


@router.delete("/skills/{task_type}")
async def delete_skill_profile(
    task_type: str,
    api_key: str = Depends(verify_api_key),
):
    """Delete a skill profile entry by task type."""
    normalized = task_type.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="task_type is required")
    try:
        await execute("DELETE FROM skills WHERE task_type = $1", normalized)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not connected")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not delete skill: {e}")

    return {"status": "deleted", "task_type": normalized}


@router.get("/decisions")
async def get_decision_analytics(
    days: int = 30, api_key: str = Depends(verify_api_key)
):
    """Decision patterns: most common choices and confidence by decision point."""
    safe_days = min(max(days, 1), 180)
    try:
        rows = await fetch(
            """
            SELECT
                decision_point,
                chosen,
                COUNT(*) AS times_chosen,
                AVG(confidence) AS avg_confidence,
                COUNT(*) FILTER (WHERE outcome = 'success') AS successes,
                COUNT(*) FILTER (WHERE outcome = 'failure') AS failures
            FROM decisions
            WHERE created_at >= NOW() - ($1::int * INTERVAL '1 day')
            GROUP BY decision_point, chosen
            ORDER BY decision_point, times_chosen DESC
            """,
            safe_days,
        )
    except Exception:
        return {"days": safe_days, "decisions": []}

    decisions = [
        {
            "decision_point": r["decision_point"],
            "chosen": r["chosen"],
            "times_chosen": int(r["times_chosen"] or 0),
            "avg_confidence": round(float(r["avg_confidence"] or 0), 3),
            "successes": int(r["successes"] or 0),
            "failures": int(r["failures"] or 0),
        }
        for r in rows
    ]
    return {"days": safe_days, "decisions": decisions}


@router.get("/errors")
async def get_error_analytics(days: int = 30, api_key: str = Depends(verify_api_key)):
    """Error pattern breakdown: frequency, models affected, recovery outcomes."""
    safe_days = min(max(days, 1), 180)
    try:
        rows = await fetch(
            """
            SELECT
                error_type,
                recovery_strategy,
                model_used,
                COUNT(*) AS occurrences,
                COUNT(*) FILTER (WHERE recovery_successful = true) AS recovered
            FROM error_patterns
            WHERE created_at >= NOW() - ($1::int * INTERVAL '1 day')
            GROUP BY error_type, recovery_strategy, model_used
            ORDER BY occurrences DESC
            LIMIT 50
            """,
            safe_days,
        )
    except Exception:
        return {"days": safe_days, "patterns": []}

    patterns = [
        {
            "error_type": r["error_type"],
            "recovery_strategy": r["recovery_strategy"],
            "model_used": r["model_used"],
            "occurrences": int(r["occurrences"] or 0),
            "recovered": int(r["recovered"] or 0),
        }
        for r in rows
    ]
    return {"days": safe_days, "patterns": patterns}


@router.get("/cost-efficiency")
async def get_cost_efficiency(api_key: str = Depends(verify_api_key)):
    """
    Quality-per-dollar breakdown by model, derived from task_feedback signals.
    Returns the in-memory efficiency cache populated by cost_learning.
    """
    scores = get_efficiency_scores()
    if not scores:
        return {
            "note": "No efficiency data yet — run tasks and give feedback to populate.",
            "models": [],
        }

    ranked = sorted(scores.values(), key=lambda s: s.efficiency, reverse=True)
    return {
        "models": [
            {
                "model": s.model,
                "avg_cost_per_task": round(s.avg_cost, 6),
                "thumbs_up_rate": round(s.thumbs_up_rate, 3),
                "efficiency_score": round(s.efficiency, 2),
                "sample_count": s.sample_count,
                "last_updated": s.last_updated.isoformat(),
            }
            for s in ranked
        ]
    }


@router.get("/ab-tests")
async def get_ab_tests(limit: int = 20, api_key: str = Depends(verify_api_key)):
    """Recent A/B test results with winner breakdown."""
    safe_limit = min(max(limit, 1), 100)
    try:
        rows = await fetch(
            """
            SELECT task_description, approach_a, approach_b,
                   result_a, result_b, winner, win_reason, created_at
            FROM ab_tests
            ORDER BY created_at DESC
            LIMIT $1
            """,
            safe_limit,
        )
    except Exception:
        return {"tests": []}

    tests = []
    for r in rows:
        ra = json.loads(r["result_a"] or "{}")
        rb = json.loads(r["result_b"] or "{}")
        tests.append(
            {
                "task": r["task_description"],
                "approach_a": json.loads(r["approach_a"] or "{}"),
                "approach_b": json.loads(r["approach_b"] or "{}"),
                "result_a": {
                    "cost": ra.get("cost"),
                    "time_ms": ra.get("time_ms"),
                    "success": ra.get("success"),
                },
                "result_b": {
                    "cost": rb.get("cost"),
                    "time_ms": rb.get("time_ms"),
                    "success": rb.get("success"),
                },
                "winner": r["winner"],
                "win_reason": r["win_reason"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return {"tests": tests}


@router.post("/ab-tests/run")
async def trigger_ab_test(
    task: str,
    model_a: str,
    model_b: str,
    system_prompt_a: str = "",
    system_prompt_b: str = "",
    api_key: str = Depends(verify_api_key),
):
    """
    Run the same task against two model configurations and record the winner.
    Results are persisted to ab_tests and returned immediately.
    """
    if not task.strip():
        raise HTTPException(status_code=400, detail="task must not be empty")
    result = await run_ab_test(
        task_description=task,
        approach_a={"model": model_a, "system_prompt": system_prompt_a},
        approach_b={"model": model_b, "system_prompt": system_prompt_b},
    )
    return result
