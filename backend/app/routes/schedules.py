"""
User-defined cron schedules → rows in ``scheduled_tasks``, dispatched by
:class:`OrchestrationRuntime` (``user_cron_dispatch`` interval job).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.database import fetch, fetchrow
from app import database as _db
from app.models import ScheduledTaskCreate
from app.utils.auth import verify_api_key
from app.utils.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _validate_cron(expr: str) -> None:
    try:
        from croniter import croniter
    except ImportError as e:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="croniter is not installed — cannot validate schedules",
        ) from e
    try:
        croniter(expr.strip(), datetime.utcnow())
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid cron expression: {e}"
        ) from e


class ScheduledTaskOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    cron_expr: str
    prompt: str
    context: Optional[str] = None
    router_tier: Optional[str] = None
    max_iterations: int = 10
    enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: datetime
    created_at: Optional[datetime] = None


class ScheduleCreateResponse(BaseModel):
    id: str
    next_run_at: datetime


@router.post("", response_model=ScheduleCreateResponse)
@limiter.limit("30/minute")
async def create_schedule(
    request: Request,
    body: ScheduledTaskCreate,
    api_key: str = Depends(verify_api_key),
):
    if not _db.db_pool:
        raise HTTPException(status_code=503, detail="Database required for schedules")
    _validate_cron(body.cron)
    from croniter import croniter

    now = datetime.utcnow()
    next_run = croniter(body.cron.strip(), now).get_next(datetime)

    row = await fetchrow(
        """
        INSERT INTO scheduled_tasks
            (user_id, cron_expr, prompt, context, router_tier, max_iterations, enabled, next_run_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, next_run_at
        """,
        body.user_id,
        body.cron.strip(),
        body.prompt,
        body.context,
        body.router_tier,
        body.max_iterations,
        body.enabled,
        next_run,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create schedule")
    return ScheduleCreateResponse(id=str(row["id"]), next_run_at=row["next_run_at"])


@router.get("", response_model=list[ScheduledTaskOut])
@limiter.limit("60/minute")
async def list_schedules(
    request: Request,
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    api_key: str = Depends(verify_api_key),
):
    if not _db.db_pool:
        raise HTTPException(status_code=503, detail="Database required for schedules")
    if user_id is not None:
        rows = await fetch(
            """
            SELECT id, user_id, cron_expr, prompt, context, router_tier, max_iterations,
                   enabled, last_run_at, next_run_at, created_at
            FROM scheduled_tasks
            WHERE user_id IS NOT DISTINCT FROM $1
            ORDER BY created_at DESC NULLS LAST
            LIMIT $2
            """,
            user_id,
            limit,
        )
    else:
        rows = await fetch(
            """
            SELECT id, user_id, cron_expr, prompt, context, router_tier, max_iterations,
                   enabled, last_run_at, next_run_at, created_at
            FROM scheduled_tasks
            ORDER BY created_at DESC NULLS LAST
            LIMIT $1
            """,
            limit,
        )
    out: list[ScheduledTaskOut] = []
    for r in rows:
        out.append(
            ScheduledTaskOut(
                id=str(r["id"]),
                user_id=r["user_id"],
                cron_expr=r["cron_expr"],
                prompt=r["prompt"],
                context=r["context"],
                router_tier=r["router_tier"],
                max_iterations=int(r["max_iterations"] or 10),
                enabled=bool(r["enabled"]),
                last_run_at=r["last_run_at"],
                next_run_at=r["next_run_at"],
                created_at=r["created_at"],
            )
        )
    return out


@router.delete("/{schedule_id}")
@limiter.limit("30/minute")
async def delete_schedule(
    request: Request,
    schedule_id: UUID,
    user_id: Optional[str] = Query(None),
    api_key: str = Depends(verify_api_key),
):
    if not _db.db_pool:
        raise HTTPException(status_code=503, detail="Database required for schedules")
    row = await fetchrow(
        """
        DELETE FROM scheduled_tasks
        WHERE id = $1
          AND ($2::text IS NULL OR user_id IS NOT DISTINCT FROM $2)
        RETURNING id
        """,
        schedule_id,
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted", "id": str(row["id"])}
