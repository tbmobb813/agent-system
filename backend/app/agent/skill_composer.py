"""
Skill Composer — named, ordered tool-chain hints for the ReAct loop.

A skill chain is a user-defined or auto-generated sequence of tool calls
that has proven effective for a particular task type. When the orchestrator
detects a matching query it injects the chain as a <skill_plan> block in the
system prompt, giving the LLM a strong (but non-binding) execution plan.

Outcomes are tracked so chains improve over time via record_chain_outcome().
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from app import database as _db
from app.agent.skill_registry import classify_query

logger = logging.getLogger(__name__)


# ── Data helpers ──────────────────────────────────────────────────────────────

def _row_to_chain(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"] or "",
        "task_type": row["task_type"],
        "steps": json.loads(row["steps"]) if isinstance(row["steps"], str) else (row["steps"] or []),
        "trigger_keywords": json.loads(row["trigger_keywords"]) if isinstance(row["trigger_keywords"], str) else (row["trigger_keywords"] or []),
        "success_rate": row["success_rate"],
        "total_runs": row["total_runs"] or 0,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


# ── Core API ──────────────────────────────────────────────────────────────────

async def list_chains() -> list[dict]:
    """Return all skill chains ordered by success rate."""
    if not _db.db_pool:
        return []
    try:
        rows = await _db.fetch(
            "SELECT * FROM skill_chains ORDER BY success_rate DESC NULLS LAST, total_runs DESC"
        )
        return [_row_to_chain(r) for r in rows]
    except Exception as e:
        logger.debug("list_chains failed: %s", e)
        return []


async def get_applicable_chain(query: str) -> Optional[dict]:
    """
    Find the best matching skill chain for a query.
    Matches on task_type first, then trigger_keywords.
    Returns None if no chain is found or DB is unavailable.
    """
    if not _db.db_pool:
        return None
    task_type = classify_query(query)
    lower = query.lower()
    try:
        rows = await _db.fetch(
            """
            SELECT * FROM skill_chains
            WHERE task_type = $1
            ORDER BY
                CASE WHEN success_rate IS NOT NULL THEN success_rate ELSE 0.5 END DESC,
                total_runs DESC
            LIMIT 5
            """,
            task_type,
        )
    except Exception as e:
        logger.debug("get_applicable_chain DB query failed: %s", e)
        return None

    # Prefer a chain whose trigger_keywords also match the query
    best = None
    best_keyword_hits = -1
    for row in rows:
        chain = _row_to_chain(row)
        keywords: list[str] = chain["trigger_keywords"]
        hits = sum(1 for kw in keywords if kw.lower() in lower)
        if hits > best_keyword_hits or best is None:
            best = chain
            best_keyword_hits = hits

    return best


async def create_chain(
    name: str,
    task_type: str,
    steps: list[dict],
    description: str = "",
    trigger_keywords: Optional[list[str]] = None,
) -> dict:
    """Insert a new skill chain and return it."""
    chain_id = str(uuid.uuid4())
    steps_json = json.dumps(steps)
    keywords_json = json.dumps(trigger_keywords or [])
    await _db.execute(
        """
        INSERT INTO skill_chains (id, name, description, task_type, steps, trigger_keywords)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        chain_id, name, description, task_type, steps_json, keywords_json,
    )
    row = await _db.fetchrow("SELECT * FROM skill_chains WHERE id = $1", chain_id)
    return _row_to_chain(row)


async def update_chain(
    chain_id: str,
    *,
    steps: Optional[list[dict]] = None,
    description: Optional[str] = None,
    trigger_keywords: Optional[list[str]] = None,
) -> Optional[dict]:
    """Update mutable fields on an existing skill chain. Returns updated chain or None."""
    sets: list[str] = ["updated_at = NOW()"]
    params: list[Any] = []
    idx = 1
    if steps is not None:
        sets.append(f"steps = ${idx}")
        params.append(json.dumps(steps))
        idx += 1
    if description is not None:
        sets.append(f"description = ${idx}")
        params.append(description)
        idx += 1
    if trigger_keywords is not None:
        sets.append(f"trigger_keywords = ${idx}")
        params.append(json.dumps(trigger_keywords))
        idx += 1
    if len(sets) == 1:
        row = await _db.fetchrow("SELECT * FROM skill_chains WHERE id = $1", chain_id)
        return _row_to_chain(row) if row else None
    params.append(chain_id)
    await _db.execute(
        f"UPDATE skill_chains SET {', '.join(sets)} WHERE id = ${idx}",
        *params,
    )
    row = await _db.fetchrow("SELECT * FROM skill_chains WHERE id = $1", chain_id)
    return _row_to_chain(row) if row else None


async def delete_chain(chain_id: str) -> bool:
    """Delete a skill chain by ID. Returns True if a row was deleted."""
    result = await _db.execute(
        "DELETE FROM skill_chains WHERE id = $1", chain_id
    )
    return "DELETE 1" in (result or "")


async def record_chain_outcome(chain_id: str, success: bool) -> None:
    """
    Update a chain's running success rate after a task that used it completes.
    Uses an exponential moving average so recent outcomes carry more weight.
    """
    if not _db.db_pool:
        return
    try:
        row = await _db.fetchrow(
            "SELECT success_rate, total_runs FROM skill_chains WHERE id = $1",
            chain_id,
        )
        if not row:
            return
        prev = row["success_rate"]
        runs = (row["total_runs"] or 0) + 1
        outcome = 1.0 if success else 0.0
        # EMA with alpha = 0.2 once we have 5+ runs, else simple average
        if prev is None or runs <= 5:
            new_rate = ((prev or 0.0) * (runs - 1) + outcome) / runs
        else:
            new_rate = 0.8 * prev + 0.2 * outcome
        await _db.execute(
            """
            UPDATE skill_chains
            SET success_rate = $1, total_runs = $2, updated_at = NOW()
            WHERE id = $3
            """,
            round(new_rate, 4), runs, chain_id,
        )
    except Exception as e:
        logger.debug("record_chain_outcome failed: %s", e)


# ── Auto-generation from tool_recommendations ─────────────────────────────────

_STEP_DESCRIPTIONS: dict[str, str] = {
    "web_search": "Search the web for current information",
    "mcp_brave_search_brave_web_search": "Search the web via Brave Search",
    "mcp_brave_search_brave_local_search": "Search for local businesses and places",
    "browser_automation": "Browse a specific URL for detailed content",
    "code_execution": "Execute code to compute or verify results",
    "file_operations": "Read or write files in the workspace",
    "search_documents": "Search uploaded documents for relevant context",
    "memory_save": "Save key findings to memory for future reference",
    "api_call": "Make an external API call",
    "github": "Interact with GitHub repositories",
    "delegate_sub_agent": "Delegate a sub-task to a specialised agent",
}


async def auto_generate_chains(min_occurrences: int = 5) -> list[dict]:
    """
    Promote tool_recommendations entries into skill_chains when they have
    enough sample data and no chain for that task_type already exists.
    Returns the list of newly created chains.
    """
    if not _db.db_pool:
        return []
    try:
        recs = await _db.fetch(
            """
            SELECT tr.task_type, tr.recommended_sequence, tr.sample_count, tr.success_rate
            FROM tool_recommendations tr
            WHERE tr.sample_count >= $1
              AND NOT EXISTS (
                SELECT 1 FROM skill_chains sc WHERE sc.task_type = tr.task_type
              )
            ORDER BY tr.sample_count DESC
            """,
            min_occurrences,
        )
    except Exception as e:
        logger.debug("auto_generate_chains query failed: %s", e)
        return []

    created: list[dict] = []
    for row in recs:
        task_type: str = row["task_type"]
        tools: list[str] = json.loads(row["recommended_sequence"] or "[]")
        if not tools:
            continue
        steps = [
            {
                "tool": t,
                "description": _STEP_DESCRIPTIONS.get(t, f"Use {t}"),
            }
            for t in tools
        ]
        name = f"{task_type}_auto"
        description = (
            f"Auto-generated from {row['sample_count']} past {task_type} tasks "
            f"(success rate: {round((row['success_rate'] or 1.0) * 100):.0f}%)"
        )
        try:
            chain = await create_chain(
                name=name,
                task_type=task_type,
                steps=steps,
                description=description,
            )
            # Seed the success rate from historical data
            if row["success_rate"] is not None:
                await _db.execute(
                    "UPDATE skill_chains SET success_rate = $1 WHERE id = $2",
                    round(float(row["success_rate"]), 4),
                    chain["id"],
                )
                chain["success_rate"] = round(float(row["success_rate"]), 4)
            created.append(chain)
        except Exception as e:
            logger.debug("auto_generate_chains create failed for %s: %s", task_type, e)

    return created


# ── Prompt formatting ─────────────────────────────────────────────────────────

def format_chain_hint(chain: dict) -> str:
    """
    Format a skill chain as a <skill_plan> XML block for injection into
    the system prompt. Strong hint, not a hard constraint.
    """
    steps: list[dict] = chain.get("steps") or []
    if not steps:
        return ""

    lines = [
        f'<skill_plan name="{chain["name"]}">',
        f'Proven sequence for {chain["task_type"]} tasks'
        + (
            f' ({round(chain["success_rate"] * 100):.0f}% success, {chain["total_runs"]} runs)'
            if chain.get("success_rate") is not None and chain.get("total_runs", 0) > 0
            else ""
        ) + ":",
    ]
    for i, step in enumerate(steps, 1):
        tool = step.get("tool", "")
        desc = step.get("description", "")
        hint = step.get("hint", "")
        line = f"  {i}. {tool}"
        if desc:
            line += f" — {desc}"
        if hint:
            line += f" ({hint})"
        lines.append(line)
    lines.append(
        "Follow this sequence unless the specific task clearly warrants a different approach."
    )
    lines.append("</skill_plan>")
    return "\n".join(lines)
