"""
Tool Learning — finds the most effective tool sequences for each task type
and surfaces them as prompt hints so the agent can skip trial-and-error.

learn_tool_chains() is a background job that mines `tool_calls` + `tasks`
and upserts into `tool_recommendations`.

get_tool_hint(query) is called at prompt-build time to inject a short hint
like "For coding tasks, tools that tend to work well: web_search, code_runner"
— it never blocks; returns "" on any failure.
"""

import json
import logging
from collections import Counter
from app import database as _db
from app.agent.skill_registry import classify_query

logger = logging.getLogger(__name__)

# Minimum successful tasks before we trust a recommendation
MIN_SAMPLE_SIZE = 5
# Max tools to mention in a hint (keeps it concise)
MAX_HINT_TOOLS = 4


async def learn_tool_chains() -> None:
    """
    Mine tool sequences from completed tasks and upsert recommendations.
    Safe to call repeatedly — uses ON CONFLICT DO UPDATE.
    """
    if not _db.db_pool:
        return

    try:
        rows = await _db.fetch("""
            SELECT t.query, tc.tool_name
            FROM tool_calls tc
            JOIN tasks t ON t.id::text = tc.task_id
            WHERE t.status = 'completed'
              AND t.created_at > NOW() - INTERVAL '30 days'
            ORDER BY tc.task_id, tc.iteration
            """)
    except Exception as e:
        logger.debug(f"Tool chain mining failed: {e}")
        return

    # Group tool names per (task_type, task_id) — preserve call order
    type_sequences: dict[str, list[list[str]]] = {}
    current_task_tools: dict[str, tuple[str, list[str]]] = (
        {}
    )  # task_key → (type, [tools])

    for row in rows:
        query = row["query"] or ""
        task_type = classify_query(query)
        tool = row["tool_name"]
        # Use query as a proxy for task identity within the result set
        key = query[:100]
        if key not in current_task_tools:
            current_task_tools[key] = (task_type, [])
        current_task_tools[key][1].append(tool)

    for _key, (task_type, tools) in current_task_tools.items():
        type_sequences.setdefault(task_type, []).append(tools)

    for task_type, sequences in type_sequences.items():
        if len(sequences) < MIN_SAMPLE_SIZE:
            continue

        # Find most common individual tools (not full sequences — too sparse)
        all_tools: list[str] = [t for seq in sequences for t in seq]
        top_tools = [tool for tool, _ in Counter(all_tools).most_common(MAX_HINT_TOOLS)]

        # Success rate = all these sequences came from completed tasks
        success_rate = 1.0  # already filtered to completed tasks above

        try:
            await _db.execute(
                """
                INSERT INTO tool_recommendations
                    (task_type, recommended_sequence, success_rate, sample_count, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (task_type) DO UPDATE SET
                    recommended_sequence = EXCLUDED.recommended_sequence,
                    success_rate         = EXCLUDED.success_rate,
                    sample_count         = EXCLUDED.sample_count,
                    updated_at           = NOW()
                """,
                task_type,
                json.dumps(top_tools),
                round(success_rate, 3),
                len(sequences),
            )
        except Exception as e:
            logger.debug(f"Tool recommendation upsert failed for {task_type}: {e}")

    logger.info(
        f"Tool chain learning complete: {len(type_sequences)} task types analysed"
    )


async def get_tool_hint(query: str) -> str:
    """
    Return a one-line tool hint for the given query, or "" if none available.
    Used to inject a soft suggestion into the system prompt.
    """
    if not _db.db_pool:
        return ""

    task_type = classify_query(query)
    if task_type == "general":
        return ""

    try:
        row = await _db.fetchrow(
            """
            SELECT recommended_sequence, sample_count
            FROM tool_recommendations
            WHERE task_type = $1
            """,
            task_type,
        )
    except Exception as e:
        logger.debug(f"Tool hint lookup failed: {e}")
        return ""

    if not row:
        return ""

    tools: list[str] = json.loads(row["recommended_sequence"] or "[]")
    if not tools:
        return ""

    count = row["sample_count"] or 0
    tools_str = ", ".join(tools)
    return (
        f"For {task_type} tasks (based on {count} past successful runs), "
        f"these tools tend to be effective: {tools_str}."
    )
