"""
Analytics routes for cost, performance, and tool usage insights.
"""

from calendar import monthrange
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import fetch, fetchval
from app.utils.auth import verify_api_key

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
