"""
History routes — modular APIRouter for /history/* endpoints.

To wire into main.py:
    from app.routes.history import router as history_router
    app.include_router(history_router)
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from typing import Literal
from pydantic import BaseModel, Field

from app.database import fetch, fetchrow, fetchval, execute
from app.agent.memory import memory_manager
from app.utils.auth import verify_api_key

router = APIRouter(prefix="/history", tags=["history"])
logger = logging.getLogger(__name__)


class TaskFeedbackRequest(BaseModel):
    signal: Literal["up", "down"]
    notes: Optional[str] = Field(default=None, max_length=1000)


@router.get("")
async def get_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, max_length=500),
    api_key: str = Depends(verify_api_key),
):
    """
    Paginated history grouped by conversation thread.

    Each entry is either:
      - type "thread": multiple tasks sharing a conversation_id, shown as one row
      - type "task": a standalone task with no conversation_id
    Search falls back to a flat per-task view so individual messages are findable.
    """
    if q and q.strip():
        # Search: flat per-task results using the GIN full-text index
        # tasks_query_result_fts (created in migration 010).
        # The WHERE expression to_tsvector('english', coalesce(...) || ' ' || coalesce(...))
        # exactly matches the index definition so PostgreSQL uses the GIN index
        # rather than a full table scan.
        tsq = q.strip()
        rows = await fetch(
            """
            SELECT
                'task'          AS entry_type,
                t.id::text      AS id,
                t.conversation_id,
                t.query,
                1               AS message_count,
                COALESCE(t.cost, 0) AS total_cost,
                t.created_at,
                t.created_at    AS updated_at,
                t.status,
                t.model_used,
                (
                    SELECT tf.signal FROM task_feedback tf
                    WHERE tf.task_id = t.id
                    ORDER BY tf.created_at DESC LIMIT 1
                ) AS feedback_signal
            FROM tasks t
            WHERE to_tsvector('english',
                      coalesce(t.query, '') || ' ' || coalesce(t.result, ''))
                  @@ plainto_tsquery('english', $3)
            ORDER BY t.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
            tsq,
        )
        total = await fetchval(
            """
            SELECT COUNT(*) FROM tasks
            WHERE to_tsvector('english',
                      coalesce(query, '') || ' ' || coalesce(result, ''))
                  @@ plainto_tsquery('english', $1)
            """,
            tsq,
        )
        return {
            "tasks": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # Default: group threads, mix with standalone tasks
    rows = await fetch(
        """
        WITH thread_agg AS (
            SELECT
                conversation_id,
                (array_agg(id::text   ORDER BY created_at ASC))[1]  AS first_id,
                (array_agg(query      ORDER BY created_at ASC))[1]  AS first_query,
                COUNT(*)::int                                         AS message_count,
                COALESCE(SUM(cost), 0)                               AS total_cost,
                MIN(created_at)                                       AS created_at,
                MAX(created_at)                                       AS updated_at,
                (array_agg(status     ORDER BY created_at DESC))[1] AS latest_status,
                (array_agg(model_used ORDER BY created_at DESC))[1] AS model_used
            FROM tasks
            WHERE conversation_id IS NOT NULL
            GROUP BY conversation_id
        ),
        standalone AS (
            SELECT
                id::text        AS id,
                query,
                COALESCE(cost, 0) AS cost,
                created_at,
                status,
                model_used,
                (
                    SELECT tf.signal FROM task_feedback tf
                    WHERE tf.task_id = tasks.id
                    ORDER BY tf.created_at DESC LIMIT 1
                ) AS feedback_signal
            FROM tasks
            WHERE conversation_id IS NULL
        ),
        combined AS (
            SELECT
                'thread'            AS entry_type,
                NULL                AS id,
                ta.conversation_id,
                ta.first_query      AS query,
                ta.message_count,
                ta.total_cost,
                ta.created_at,
                ta.updated_at,
                ta.latest_status    AS status,
                ta.model_used,
                NULL                AS feedback_signal
            FROM thread_agg ta

            UNION ALL

            SELECT
                'task'              AS entry_type,
                s.id,
                NULL                AS conversation_id,
                s.query,
                1                   AS message_count,
                s.cost              AS total_cost,
                s.created_at,
                s.created_at        AS updated_at,
                s.status,
                s.model_used,
                s.feedback_signal
            FROM standalone s
        )
        SELECT * FROM combined
        ORDER BY updated_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    total = await fetchval("""
        SELECT (
            (SELECT COUNT(DISTINCT conversation_id) FROM tasks WHERE conversation_id IS NOT NULL)
            + (SELECT COUNT(*) FROM tasks WHERE conversation_id IS NULL)
        )
        """)
    return {
        "tasks": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation_thread(
    conversation_id: str, api_key: str = Depends(verify_api_key)
):
    """Return all tasks in a conversation thread, oldest first."""
    rows = await fetch(
        """
        SELECT
            t.id,
            t.query,
            t.status,
            t.result,
            t.created_at,
            t.completed_at,
            t.execution_time,
            t.cost,
            t.model_used,
            (
                SELECT tf.signal FROM task_feedback tf
                WHERE tf.task_id = t.id
                ORDER BY tf.created_at DESC LIMIT 1
            ) AS feedback_signal
        FROM tasks t
        WHERE t.conversation_id = $1
        ORDER BY t.created_at ASC
        """,
        conversation_id,
    )
    return {"conversation_id": conversation_id, "messages": [dict(r) for r in rows]}


@router.get("/{task_id}")
async def get_task_detail(task_id: str, api_key: str = Depends(verify_api_key)):
    """Get a specific task with its execution steps."""
    task = await fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    steps = await fetch(
        "SELECT * FROM task_steps WHERE task_id = $1 ORDER BY step_number ASC",
        task_id,
    )
    feedback = await fetchrow(
        """
        SELECT signal, notes, created_at
        FROM task_feedback
        WHERE task_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        task_id,
    )
    return {
        "task": dict(task),
        "steps": [dict(s) for s in steps],
        "feedback": dict(feedback) if feedback else None,
    }


@router.post("/{task_id}/feedback")
async def submit_task_feedback(
    task_id: str,
    body: TaskFeedbackRequest,
    api_key: str = Depends(verify_api_key),
):
    """Store explicit user feedback for a completed task and promote note-based learning."""
    task = await fetchrow(
        "SELECT id, query, user_id, status FROM tasks WHERE id = $1", task_id
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_status = task.get("status") if isinstance(task, dict) else task["status"]
    if task_status != "completed":
        raise HTTPException(
            status_code=409, detail="Feedback can only be submitted for completed tasks"
        )

    task_user_id = task.get("user_id") if isinstance(task, dict) else task["user_id"]
    task_query = task.get("query") if isinstance(task, dict) else task["query"]
    notes = (body.notes or "").strip() or None
    saved_feedback = await fetchrow(
        """
        INSERT INTO task_feedback (task_id, user_id, signal, notes)
        VALUES ($1, $2, $3, $4)
        RETURNING signal, notes, created_at
        """,
        task_id,
        task_user_id,
        body.signal,
        notes,
    )
    if not saved_feedback:
        raise HTTPException(status_code=500, detail="Failed to store feedback")

    if notes:
        try:
            await memory_manager.save_feedback_learning(
                task_query=task_query,
                signal=body.signal,
                notes=notes,
                user_id=task_user_id,
            )
        except Exception as e:
            # Log promotion failure but don't fail the request—feedback is already recorded
            logger.warning(
                "Feedback learning promotion failed for task %s: %s", task_id, e
            )

    # ── #7 Implicit preference learning: attribute outcome to tools used ──────
    import asyncio as _asyncio
    from app.agent.tool_preferences import record_tool_outcome

    _asyncio.create_task(record_tool_outcome(task_id, body.signal, task_user_id))

    return {
        "status": "recorded",
        "task_id": task_id,
        "signal": saved_feedback["signal"],
        "notes": saved_feedback["notes"],
        "created_at": saved_feedback["created_at"],
    }


@router.delete("/{task_id}")
async def delete_task(task_id: str, api_key: str = Depends(verify_api_key)):
    """Delete a task and its steps from history."""
    await execute("DELETE FROM task_steps WHERE task_id = $1", task_id)
    await execute("DELETE FROM tasks WHERE id = $1", task_id)
    return {"status": "deleted", "task_id": task_id}
