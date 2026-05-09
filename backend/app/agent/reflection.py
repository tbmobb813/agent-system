"""
Post-Task Reflection — the agent evaluates its own performance after each run.

Flow:
  1. Compose a structured self-evaluation prompt from the task and result.
  2. Call the cheap model to produce the reflection (non-blocking).
  3. Store the full reflection in the `reflections` table.
  4. Extract generalizable rules and save them as `pattern` memories so the
     existing context_builder pipeline surfaces them in future prompts automatically.
"""

import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app import database as _db

logger = logging.getLogger(__name__)

_REFLECTION_PROMPT = """\
You just completed a task. Evaluate your own performance honestly and briefly.

Task: {query}

Result (first 600 chars): {result_preview}
Success: {success}
Model used: {model_used}
Tools used: {tools_used}

Answer these questions concisely:
1. What went well?
2. What could be improved?
3. What would you do differently next time?
4. Were the right tools chosen for this task?
5. Rate your confidence in the result (1–10).

Then output a JSON block with this exact structure (nothing else after it):
```json
{{
  "self_rating": <1-10 integer>,
  "learned_rules": [
    "<one generalizable rule per string, e.g. 'For code tasks, always verify syntax before returning'>",
    ...
  ]
}}
```"""

_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": "Personal AI Agent",
        },
    )


async def post_task_reflection(
    task_id: str,
    query: str,
    result: str,
    success: bool = True,
    model_used: str = "",
    tools_used: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Run a self-evaluation for the completed task and persist the findings.
    Designed to be called via asyncio.create_task() — never raises.
    """
    if not settings.OPENROUTER_API_KEY:
        return

    tools_str = ", ".join(tools_used) if tools_used else "none"
    result_preview = result[:600] if result else "(empty)"

    prompt = _REFLECTION_PROMPT.format(
        query=query[:400],
        result_preview=result_preview,
        success=success,
        model_used=model_used,
        tools_used=tools_str,
    )

    try:
        client = _openrouter_client()
        resp = await client.chat.completions.create(
            model=settings.DEFAULT_MODEL_SIMPLE,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0,
        )
        reflection_text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.debug(f"Reflection LLM call failed (non-critical): {e}")
        return

    # Parse structured block
    self_rating: Optional[int] = None
    learned_rules: list[str] = []

    match = _JSON_RE.search(reflection_text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            raw_rating = parsed.get("self_rating")
            if isinstance(raw_rating, (int, float)):
                self_rating = max(1, min(10, int(raw_rating)))
            rules = parsed.get("learned_rules", [])
            if isinstance(rules, list):
                learned_rules = [r for r in rules if isinstance(r, str) and r.strip()]
        except (json.JSONDecodeError, ValueError):
            pass

    # Persist reflection record
    if _db.db_pool:
        try:
            await _db.execute(
                """
                INSERT INTO reflections
                    (task_id, user_id, query, result_summary,
                     reflection_text, learned_rules, self_rating)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (task_id) DO NOTHING
                """,
                task_id,
                user_id,
                query[:500],
                result_preview,
                reflection_text[:4000],
                json.dumps(learned_rules),
                self_rating,
            )
        except Exception as e:
            logger.debug(f"Reflection DB insert failed (non-critical): {e}")

    # Promote generalizable rules into the memory table so context_builder
    # surfaces them as few-shot examples in future similar tasks.
    if learned_rules:
        from app.agent.memory import memory_manager

        for rule in learned_rules[:3]:  # cap to avoid bloat
            rule = rule.strip()
            if len(rule) < 10:
                continue
            await memory_manager.save(
                content=f"[Learned rule] {rule}",
                category="pattern",
                user_id=user_id,
                relevance_score=1.1,
            )
        logger.info(
            f"Reflection complete for task {task_id}: rating={self_rating}, rules={len(learned_rules)}"
        )
