"""
Skill Registry — tracks what task types the agent handles well.

Background job (update_skills) reads completed tasks, computes success rates
per task type, and upserts into the `skills` table.  The registry uses simple
keyword matching to classify queries into task types — no LLM call needed.

get_agent_profile() is consumed by the /analytics/skills endpoint.

The registry runs its update at most once every REFRESH_INTERVAL_HOURS so it
is safe to call from the orchestrator on every startup without hammering the DB.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from app import database as _db

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS = 6
MIN_SAMPLE_SIZE = 3  # ignore task types with fewer examples
EXPERT_THRESHOLD = 0.85
COMPETENT_THRESHOLD = 0.65

# Keyword → task_type mapping (first match wins, checked in order).
_TASK_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "coding",
        [
            "code",
            "function",
            "class",
            "method",
            "bug",
            "debug",
            "implement",
            "python",
            "javascript",
            "typescript",
            "sql",
            "script",
            "refactor",
            "test",
            "unittest",
            "error in",
            "fix the",
            "write a program",
        ],
    ),
    (
        "research",
        [
            "research",
            "find out",
            "look up",
            "what is",
            "who is",
            "when did",
            "explain",
            "how does",
            "tell me about",
            "search for",
            "summarize the",
        ],
    ),
    (
        "analysis",
        [
            "analyze",
            "analysis",
            "compare",
            "evaluate",
            "assess",
            "review",
            "what are the differences",
            "pros and cons",
            "tradeoffs",
        ],
    ),
    (
        "writing",
        [
            "write",
            "draft",
            "compose",
            "email",
            "letter",
            "blog post",
            "summarize",
            "rewrite",
            "proofread",
            "edit this",
        ],
    ),
    (
        "automation",
        [
            "automate",
            "workflow",
            "schedule",
            "pipeline",
            "batch",
            "cron",
            "run every",
            "trigger",
            "webhook",
        ],
    ),
    (
        "data",
        [
            "data",
            "csv",
            "spreadsheet",
            "chart",
            "graph",
            "dataset",
            "calculate",
            "statistics",
            "aggregate",
            "query",
        ],
    ),
    (
        "planning",
        [
            "plan",
            "roadmap",
            "strategy",
            "outline",
            "steps to",
            "how to",
            "best way to",
            "approach for",
            "design",
        ],
    ),
]

_LAST_UPDATE: Optional[datetime] = None


def classify_query(query: str) -> str:
    """Map a raw query string to a task type using keyword matching."""
    lower = query.lower()
    for task_type, keywords in _TASK_TYPE_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return task_type
    return "general"


def _proficiency(success_rate: float) -> str:
    if success_rate >= EXPERT_THRESHOLD:
        return "expert"
    if success_rate >= COMPETENT_THRESHOLD:
        return "competent"
    return "novice"


async def update_skills() -> None:
    """
    Compute per-task-type success rates from the `tasks` table and upsert
    into `skills`.  Skips gracefully if the DB is unavailable or the data
    is too sparse.  Throttled to once per REFRESH_INTERVAL_HOURS.
    """
    global _LAST_UPDATE
    if not _db.db_pool:
        return
    if _LAST_UPDATE and datetime.utcnow() - _LAST_UPDATE < timedelta(
        hours=REFRESH_INTERVAL_HOURS
    ):
        return

    try:
        rows = await _db.fetch(
            """
            SELECT query, status, tool_calls_count
            FROM (
                SELECT
                    t.query,
                    t.status,
                    COUNT(tc.id) AS tool_calls_count
                FROM tasks t
                LEFT JOIN tool_calls tc ON tc.task_id = t.id::text
                WHERE t.created_at > NOW() - INTERVAL '30 days'
                GROUP BY t.id, t.query, t.status
            ) sub
            """
        )
    except Exception as e:
        logger.debug(f"Skill registry DB read failed: {e}")
        return

    # Bucket tasks by type and accumulate counts
    type_stats: dict[str, dict] = {}  # task_type → {total, success, tools: set}
    for row in rows:
        task_type = classify_query(row["query"] or "")
        stats = type_stats.setdefault(
            task_type, {"total": 0, "success": 0, "tools": set()}
        )
        stats["total"] += 1
        if row["status"] == "completed":
            stats["success"] += 1

    # Fetch tool names used per task type from tool_calls
    try:
        tool_rows = await _db.fetch(
            """
            SELECT t.query, tc.tool_name
            FROM tool_calls tc
            JOIN tasks t ON t.id::text = tc.task_id
            WHERE t.status = 'completed'
              AND t.created_at > NOW() - INTERVAL '30 days'
            """
        )
        for row in tool_rows:
            task_type = classify_query(row["query"] or "")
            if task_type in type_stats:
                type_stats[task_type]["tools"].add(row["tool_name"])
    except Exception as e:
        logger.debug(f"Skill registry tool fetch failed: {e}")

    now = datetime.utcnow()
    for task_type, stats in type_stats.items():
        if stats["total"] < MIN_SAMPLE_SIZE:
            continue
        success_rate = stats["success"] / stats["total"]
        skill_name = task_type.replace("_", " ").title()
        required_tools = sorted(stats["tools"])

        try:
            await _db.execute(
                """
                INSERT INTO skills
                    (task_type, skill_name, success_rate, total_uses,
                     proficiency_level, required_tools, last_computed)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (task_type) DO UPDATE SET
                    success_rate      = EXCLUDED.success_rate,
                    total_uses        = EXCLUDED.total_uses,
                    proficiency_level = EXCLUDED.proficiency_level,
                    required_tools    = EXCLUDED.required_tools,
                    last_computed     = EXCLUDED.last_computed
                """,
                task_type,
                skill_name,
                round(success_rate, 3),
                stats["total"],
                _proficiency(success_rate),
                json.dumps(required_tools),
                now,
            )
        except Exception as e:
            logger.debug(f"Skill upsert failed for {task_type}: {e}")

    _LAST_UPDATE = datetime.utcnow()
    logger.info(f"Skill registry updated: {len(type_stats)} task types processed")


async def get_agent_profile() -> dict:
    """
    Return the agent's current skill profile for the dashboard.
    Structure mirrors the Phase 1 plan's /analytics/skills shape.
    """
    if not _db.db_pool:
        return {"skills": [], "growth_areas": []}

    try:
        rows = await _db.fetch(
            """
            SELECT task_type, skill_name, success_rate, total_uses,
                   proficiency_level, required_tools, last_computed
            FROM skills
            ORDER BY success_rate DESC NULLS LAST
            """
        )
    except Exception as e:
        logger.warning(f"get_agent_profile failed: {e}")
        return {"skills": [], "growth_areas": []}

    skills = []
    growth_areas = []
    for row in rows:
        entry = {
            "task_type": row["task_type"],
            "skill_name": row["skill_name"],
            "success_rate": row["success_rate"],
            "total_uses": row["total_uses"],
            "proficiency_level": row["proficiency_level"],
            "required_tools": json.loads(row["required_tools"] or "[]"),
            "last_computed": row["last_computed"].isoformat()
            if row["last_computed"]
            else None,
        }
        if (row["success_rate"] or 0) < COMPETENT_THRESHOLD:
            growth_areas.append(entry)
        else:
            skills.append(entry)

    return {"skills": skills, "growth_areas": growth_areas}
