"""
History routes — modular APIRouter for /history/* endpoints.

To wire into main.py:
    from app.routes.history import router as history_router
    app.include_router(history_router)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from app.database import fetch, fetchrow, fetchval, execute
from app.utils.auth import verify_api_key

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def get_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, max_length=500),
    api_key: str = Depends(verify_api_key),
):
    """Get paginated execution history, optionally filtered by search query."""
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        tasks = await fetch(
            """
            SELECT id, query, status, created_at, cost, model_used
            FROM tasks
            WHERE query ILIKE $3 OR result ILIKE $3
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset, pattern,
        )
        total = await fetchval(
            "SELECT COUNT(*) FROM tasks WHERE query ILIKE $1 OR result ILIKE $1",
            pattern,
        )
    else:
        tasks = await fetch(
            """
            SELECT id, query, status, created_at, cost, model_used
            FROM tasks
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
        total = await fetchval("SELECT COUNT(*) FROM tasks")
    return {
        "tasks": [dict(t) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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
    return {"task": dict(task), "steps": [dict(s) for s in steps]}


@router.delete("/{task_id}")
async def delete_task(task_id: str, api_key: str = Depends(verify_api_key)):
    """Delete a task and its steps from history."""
    await execute("DELETE FROM task_steps WHERE task_id = $1", task_id)
    await execute("DELETE FROM tasks WHERE id = $1", task_id)
    return {"status": "deleted", "task_id": task_id}
