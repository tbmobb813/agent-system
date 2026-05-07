"""
Decision Tracker — fire-and-forget logging of every model/tool/approach choice.

Each decision is persisted to the `decisions` table. The outcome column is
updated by the orchestrator when the task finishes (success or failure).
Pattern extraction from decision history is deferred to Phase 2.
"""

import logging
from typing import Optional

from app import database as _db

logger = logging.getLogger(__name__)


async def log_decision(
    task_id: str,
    decision_point: str,
    chosen: str,
    reasoning: str = "",
    confidence: float = 0.8,
    options: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Insert one decision record.  Silently no-ops when the DB is unavailable
    so it never blocks or raises in the hot path.

    decision_point examples: 'model_selection', 'tool_selection', 'approach'
    """
    if not _db.db_pool:
        return
    try:
        import json
        await _db.execute(
            """
            INSERT INTO decisions
                (task_id, user_id, decision_point, options, chosen, reasoning, confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            task_id,
            user_id,
            decision_point,
            json.dumps(options or []),
            chosen[:500],
            reasoning[:1000],
            max(0.0, min(1.0, confidence)),
        )
    except Exception as e:
        logger.debug(f"Decision log failed (non-critical): {e}")


async def mark_outcome(task_id: str, outcome: str) -> None:
    """
    Update all decisions for a task with the final outcome.
    Called by the orchestrator after task completion/failure.
    outcome: 'success' | 'failure'
    """
    if not _db.db_pool:
        return
    try:
        await _db.execute(
            "UPDATE decisions SET outcome = $1 WHERE task_id = $2",
            outcome,
            task_id,
        )
    except Exception as e:
        logger.debug(f"Decision outcome update failed (non-critical): {e}")
