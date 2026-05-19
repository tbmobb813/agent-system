"""
Workflow pattern detection.

Reads from tool_recommendations (populated nightly by learn_tool_chains)
and surfaces task-type patterns that recur frequently enough to be worth
automating as a named workflow.
"""

import json
import logging
from app import database as _db

logger = logging.getLogger(__name__)

# Minimum recurrences before we suggest a workflow
MIN_OCCURRENCES = 3


async def get_workflow_suggestions(
    min_occurrences: int = MIN_OCCURRENCES,
) -> list[dict]:
    """
    Return the top recurring task patterns with their common tool sequences.
    Each entry is enough to draft a workflow YAML or inform the user.
    """
    if not _db.db_pool:
        return []
    try:
        rows = await _db.fetch(
            """
            SELECT task_type, recommended_sequence, sample_count, success_rate, updated_at
            FROM tool_recommendations
            WHERE sample_count >= $1
            ORDER BY sample_count DESC
            LIMIT 10
            """,
            min_occurrences,
        )
    except Exception as e:
        logger.debug("Workflow suggestion query failed: %s", e)
        return []

    results = []
    for row in rows:
        tools: list[str] = json.loads(row["recommended_sequence"] or "[]")
        task_type: str = row["task_type"]
        results.append(
            {
                "task_type": task_type,
                "tools": tools,
                "occurrences": row["sample_count"],
                "success_rate": round(float(row["success_rate"] or 0), 3),
                "updated_at": (
                    row["updated_at"].isoformat() if row["updated_at"] else None
                ),
                "suggested_name": f"{task_type}_workflow".replace(" ", "_").lower(),
                "suggested_query": _default_query(task_type),
            }
        )
    return results


def _default_query(task_type: str) -> str:
    """A generic prompt template for each task type, used to pre-fill a new workflow."""
    templates = {
        "coding": "Write and test the code for: {your task here}",
        "research": "Research and summarise: {your topic here}",
        "writing": "Write a clear, concise piece about: {your topic here}",
        "analysis": "Analyse and provide insights on: {your data or topic here}",
        "search": "Search for up-to-date information about: {your query here}",
        "summarisation": "Summarise the following: {paste text or describe source here}",
        "general": "Help me with: {your task here}",
    }
    return templates.get(
        task_type, f"Complete this {task_type} task: {{your task here}}"
    )
