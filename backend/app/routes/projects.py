"""
Projects — named folders that group tasks together.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import execute, fetch, fetchrow, fetchval
from app.utils.auth import verify_api_key

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    color: str = Field(default="#2be3c6", max_length=20)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, max_length=20)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_projects(api_key: str = Depends(verify_api_key)):
    """List all projects with task counts."""
    rows = await fetch("""
        SELECT
            p.id,
            p.name,
            p.description,
            p.color,
            p.created_at,
            p.updated_at,
            COUNT(t.id) FILTER (WHERE t.project_id = p.id) AS task_count
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """)
    return {
        "projects": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "description": r["description"],
                "color": r["color"],
                "task_count": r["task_count"] or 0,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("")
async def create_project(body: ProjectCreate, api_key: str = Depends(verify_api_key)):
    """Create a new project."""
    row = await fetchrow(
        """
        INSERT INTO projects (name, description, color)
        VALUES ($1, $2, $3)
        RETURNING id, name, description, color, created_at, updated_at
        """,
        body.name.strip(),
        body.description,
        body.color,
    )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "color": row["color"],
        "task_count": 0,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/{project_id}")
async def get_project(project_id: str, api_key: str = Depends(verify_api_key)):
    """Get a single project."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    row = await fetchrow(
        """
        SELECT p.id, p.name, p.description, p.color, p.created_at, p.updated_at,
               COUNT(t.id) FILTER (WHERE t.project_id = p.id) AS task_count
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        WHERE p.id = $1
        GROUP BY p.id
        """,
        pid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "color": row["color"],
        "task_count": row["task_count"] or 0,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    api_key: str = Depends(verify_api_key),
):
    """Update project name, description, or color."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    existing = await fetchrow(
        "SELECT id, name, description, color FROM projects WHERE id = $1", pid
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    new_name = body.name.strip() if body.name is not None else existing["name"]
    new_desc = (
        body.description if body.description is not None else existing["description"]
    )
    new_color = body.color if body.color is not None else existing["color"]

    row = await fetchrow(
        """
        UPDATE projects SET name = $1, description = $2, color = $3
        WHERE id = $4
        RETURNING id, name, description, color, created_at, updated_at
        """,
        new_name,
        new_desc,
        new_color,
        pid,
    )
    task_count = await fetchval("SELECT COUNT(*) FROM tasks WHERE project_id = $1", pid)
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "color": row["color"],
        "task_count": task_count or 0,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.delete("/{project_id}")
async def delete_project(project_id: str, api_key: str = Depends(verify_api_key)):
    """Delete a project. Tasks are unlinked (not deleted)."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    existing = await fetchrow("SELECT id FROM projects WHERE id = $1", pid)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    # Unlink tasks first (ON DELETE SET NULL handles this in the DB too, but be explicit)
    await execute("UPDATE tasks SET project_id = NULL WHERE project_id = $1", pid)
    await execute("DELETE FROM projects WHERE id = $1", pid)
    return {"deleted": True, "id": project_id}


@router.get("/{project_id}/tasks")
async def get_project_tasks(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key),
):
    """Get all tasks assigned to a project."""
    try:
        pid = UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    tasks = await fetch(
        """
        SELECT id, query, status, created_at, cost, model_used
        FROM tasks
        WHERE project_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        pid,
        limit,
        offset,
    )
    total = await fetchval("SELECT COUNT(*) FROM tasks WHERE project_id = $1", pid)
    return {
        "tasks": [
            {
                "id": str(t["id"]),
                "query": t["query"],
                "status": t["status"],
                "cost": float(t["cost"] or 0),
                "model_used": t["model_used"],
                "created_at": t["created_at"].isoformat() if t["created_at"] else None,
            }
            for t in tasks
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{project_id}/tasks/{task_id}")
async def assign_task(
    project_id: str,
    task_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Assign a task to a project."""
    try:
        pid = UUID(project_id)
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID")

    if not await fetchrow("SELECT id FROM projects WHERE id = $1", pid):
        raise HTTPException(status_code=404, detail="Project not found")
    if not await fetchrow("SELECT id FROM tasks WHERE id = $1", tid):
        raise HTTPException(status_code=404, detail="Task not found")

    await execute("UPDATE tasks SET project_id = $1 WHERE id = $2", pid, tid)
    return {"assigned": True, "project_id": project_id, "task_id": task_id}


@router.delete("/{project_id}/tasks/{task_id}")
async def remove_task(
    project_id: str,
    task_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Remove a task from a project."""
    try:
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    await execute(
        "UPDATE tasks SET project_id = NULL WHERE id = $1 AND project_id = $2",
        tid,
        UUID(project_id),
    )
    return {"removed": True, "task_id": task_id}
