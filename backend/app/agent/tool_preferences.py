"""
Implicit tool preference learning.

Each time a task receives thumbs-up/down feedback, every tool that was used
in that task has its acceptance counter updated. Over time this produces a
per-user acceptance_rate per tool that the orchestrator can use to bias
tool selection away from tools the user consistently dislikes.
"""

import logging
from typing import Optional
from app import database as _db

logger = logging.getLogger(__name__)

# Minimum feedback samples before we trust the acceptance rate
MIN_SAMPLES = 3


async def record_tool_outcome(
    task_id: str,
    signal: str,
    user_id: Optional[str],
) -> None:
    """
    Attribute thumbs-up/down feedback to every tool used in the task.
    Safe to fire-and-forget — never raises.
    """
    if not _db.db_pool or not user_id:
        return
    if signal not in ("up", "down"):
        return
    try:
        rows = await _db.fetch(
            "SELECT DISTINCT tool_name FROM tool_calls WHERE task_id = $1",
            task_id,
        )
        if not rows:
            return
        accepted_delta = 1 if signal == "up" else 0
        rejected_delta = 1 if signal == "down" else 0
        for row in rows:
            tool = row["tool_name"]
            await _db.execute(
                """
                INSERT INTO tool_preferences
                    (user_id, tool_name, accepted_count, rejected_count, total_count, acceptance_rate)
                VALUES ($1, $2, $3, $4, 1, $5)
                ON CONFLICT (user_id, tool_name) DO UPDATE SET
                    accepted_count  = tool_preferences.accepted_count  + $3,
                    rejected_count  = tool_preferences.rejected_count  + $4,
                    total_count     = tool_preferences.total_count     + 1,
                    acceptance_rate = (tool_preferences.accepted_count + $3)::float /
                                      NULLIF(tool_preferences.total_count + 1, 0),
                    updated_at      = NOW()
                """,
                user_id,
                tool,
                accepted_delta,
                rejected_delta,
                float(accepted_delta),
            )
    except Exception as e:
        logger.debug("Tool preference recording failed: %s", e)


async def get_tool_biases(
    user_id: Optional[str],
    min_uses: int = MIN_SAMPLES,
) -> dict[str, float]:
    """
    Return {tool_name: acceptance_rate} for tools with enough samples.
    Empty dict on any failure or insufficient data.
    """
    if not _db.db_pool or not user_id:
        return {}
    try:
        rows = await _db.fetch(
            """
            SELECT tool_name, acceptance_rate, total_count
            FROM tool_preferences
            WHERE user_id = $1 AND total_count >= $2
            ORDER BY total_count DESC
            """,
            user_id,
            min_uses,
        )
        return {row["tool_name"]: float(row["acceptance_rate"]) for row in rows}
    except Exception as e:
        logger.debug("Tool bias lookup failed: %s", e)
        return {}


def format_bias_hint(biases: dict[str, float]) -> str:
    """
    Format tool biases as a short system-prompt hint.
    Only mentions tools with meaningfully high or low acceptance.
    """
    if not biases:
        return ""
    preferred = [t for t, r in biases.items() if r >= 0.7]
    avoided = [t for t, r in biases.items() if r <= 0.35]
    parts: list[str] = []
    if preferred:
        parts.append(f"Tools the user tends to find helpful: {', '.join(preferred)}.")
    if avoided:
        parts.append(
            f"Tools the user has found less useful in the past (use sparingly or try alternatives): "
            f"{', '.join(avoided)}."
        )
    return " ".join(parts)
