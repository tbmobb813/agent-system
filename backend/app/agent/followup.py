"""
Follow-up suggestion generator — Feature #1: Anticipatory Task Chaining.

After a task completes, queries memory for similar past work and generates
2-3 concrete follow-up queries the user might want to run next.
Called as a fire-and-forget background task; never raises.
"""

import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app import database as _db

logger = logging.getLogger(__name__)

_PROMPT = """\
You just helped a user complete this task:
Task: {query}
Result summary: {result_preview}

Similar tasks they have worked on before:
{similar_tasks}

Suggest 2–3 concrete follow-up actions they are likely to want next.
Each suggestion must be a specific, immediately runnable query — not vague advice.
Keep each under 120 characters.

Reply ONLY with JSON (no fences): {{"suggestions": ["...", "...", "..."]}}
Only include 2 if a third would be redundant."""


async def generate_followup_suggestions(
    task_id: str,
    query: str,
    result: str,
    user_id: Optional[str] = None,
) -> None:
    """Generate and persist follow-up suggestions. Designed for asyncio.create_task()."""
    if not settings.OPENROUTER_API_KEY or not _db.db_pool:
        return
    try:
        from app.agent.memory import memory_manager

        similar = await memory_manager.search(query, user_id=user_id, limit=4, category="context")
        similar_lines = [
            f"- {(m.get('content') or '')[:180]}"
            for m in similar
            if (m.get("content") or "").strip()
        ]
        similar_text = "\n".join(similar_lines) if similar_lines else "No similar past tasks found."

        prompt = _PROMPT.format(
            query=query[:300],
            result_preview=(result or "")[:400],
            similar_tasks=similar_text,
        )

        client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )
        resp = await client.chat.completions.create(
            model=settings.DEFAULT_MODEL_SIMPLE,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.3,
        )
        raw = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip(), flags=re.DOTALL
        ).strip()
        data = json.loads(raw)
        suggestions = [s.strip() for s in data.get("suggestions", []) if isinstance(s, str) and s.strip()][:3]

        if suggestions:
            await _db.execute(
                """
                INSERT INTO task_suggestions (task_id, suggestions, created_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (task_id) DO UPDATE SET suggestions = EXCLUDED.suggestions
                """,
                task_id,
                json.dumps(suggestions),
            )
            logger.debug("Follow-up suggestions saved for task %s (%d)", task_id, len(suggestions))
    except Exception as e:
        logger.debug("Follow-up suggestion generation failed (non-critical): %s", e)
