"""
Cost-Quality Optimizer — learns which model gives the best value per dollar.

Uses task_feedback (thumbs up/down) as the quality proxy, joined against
tasks.cost and tasks.model_used to compute an efficiency score per model:

    efficiency = thumbs_up_rate / avg_cost_per_task

Results are stored in a module-level in-memory cache so select_model() can
read them synchronously without blocking the hot path.  The cache is refreshed
by refresh_efficiency_cache(), called as a background task by the orchestrator.

Two public helpers for the router:
  get_efficiency_scores() → dict[model, EfficiencyScore]
  suggest_model(candidate, task_type) → model string (may differ from candidate)
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional

from app import database as _db

logger = logging.getLogger(__name__)

# Minimum feedback samples before we trust the efficiency score
MIN_FEEDBACK_SAMPLES = 5
# Refresh at most once per hour
CACHE_TTL_HOURS = 1
# How much cheaper an alternative must be before we'd swap (20% cost reduction)
EFFICIENCY_SWAP_THRESHOLD = 1.20


@dataclass
class EfficiencyScore:
    model: str
    avg_cost: float
    thumbs_up_rate: float  # 0–1 from task_feedback
    sample_count: int
    efficiency: float  # thumbs_up_rate / avg_cost  (higher = better value)
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))


# Module-level cache: model_id → EfficiencyScore
_cache: dict[str, EfficiencyScore] = {}
_last_refresh: Optional[datetime] = None


async def refresh_efficiency_cache() -> None:
    """
    Pull model efficiency data from the DB and update the in-memory cache.
    Throttled to CACHE_TTL_HOURS — safe to call on every orchestrator run.
    """
    global _cache, _last_refresh

    if not _db.db_pool:
        return
    if _last_refresh and datetime.now(UTC) - _last_refresh < timedelta(
        hours=CACHE_TTL_HOURS
    ):
        return

    try:
        rows = await _db.fetch(
            """
            SELECT
                t.model_used                              AS model,
                COUNT(t.id)                               AS total_tasks,
                AVG(t.cost)                               AS avg_cost,
                COUNT(f.id)                               AS feedback_count,
                COUNT(f.id) FILTER (WHERE f.signal = 'up') AS thumbs_up
            FROM tasks t
            LEFT JOIN task_feedback f ON f.task_id = t.id
            WHERE t.status = 'completed'
              AND t.model_used IS NOT NULL
              AND t.created_at > NOW() - INTERVAL '60 days'
            GROUP BY t.model_used
            HAVING COUNT(t.id) >= $1
            """,
            MIN_FEEDBACK_SAMPLES,
        )
    except Exception as e:
        logger.debug(f"Efficiency cache refresh failed: {e}")
        return

    new_cache: dict[str, EfficiencyScore] = {}
    for row in rows:
        model = row["model"]
        avg_cost = float(row["avg_cost"] or 0.001)  # avoid div/0
        feedback_count = int(row["feedback_count"] or 0)
        thumbs_up = int(row["thumbs_up"] or 0)

        # If no feedback yet, assume neutral quality (0.5)
        thumbs_up_rate = (thumbs_up / feedback_count) if feedback_count > 0 else 0.5
        efficiency = thumbs_up_rate / max(avg_cost, 0.0001)

        new_cache[model] = EfficiencyScore(
            model=model,
            avg_cost=avg_cost,
            thumbs_up_rate=thumbs_up_rate,
            sample_count=int(row["total_tasks"] or 0),
            efficiency=efficiency,
        )

    if new_cache:
        _cache = new_cache
        _last_refresh = datetime.now(UTC)
        logger.info(f"Efficiency cache refreshed: {len(_cache)} models")


def get_efficiency_scores() -> dict[str, EfficiencyScore]:
    """Return the current in-memory efficiency cache (may be empty on first run)."""
    return dict(_cache)


def suggest_model(candidate_model: str, alternative_models: list[str]) -> str:
    """
    Given a candidate model and a list of alternatives the router considers,
    return the most efficient option if one has a materially better
    efficiency score (EFFICIENCY_SWAP_THRESHOLD times better) AND lower cost.
    Falls back to candidate if data is insufficient.
    """
    if not _cache or candidate_model not in _cache:
        return candidate_model

    candidate_score = _cache[candidate_model]
    best_model = candidate_model
    best_efficiency = candidate_score.efficiency

    for alt in alternative_models:
        if alt not in _cache:
            continue
        alt_score = _cache[alt]
        # Only swap if both cheaper AND meaningfully more efficient
        if (
            alt_score.avg_cost < candidate_score.avg_cost
            and alt_score.efficiency > best_efficiency * EFFICIENCY_SWAP_THRESHOLD
            and alt_score.sample_count >= MIN_FEEDBACK_SAMPLES
        ):
            best_model = alt
            best_efficiency = alt_score.efficiency

    if best_model != candidate_model:
        logger.info(
            f"Efficiency bias: swapping {candidate_model} → {best_model} "
            f"(efficiency {candidate_score.efficiency:.1f} → {best_efficiency:.1f})"
        )
    return best_model
