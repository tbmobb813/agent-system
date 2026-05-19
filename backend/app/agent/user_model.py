"""
Dialectic user modeling — builds and maintains a synthesized portrait of who
the user is, derived from accumulated memories.

After each task the agent fire-and-forgets ``run_dialectic_reflection``, which
reads recent memories and runs a single cheap LLM call to update (or create) a
short ``user_model`` document. That document is then injected into the system
prompt so every future run has a coherent picture of the user's goals, style,
and preferences without repeating the raw memory list.

Controlled by the ``AGENT_DIALECTIC_REFLECTION`` env flag (default False).
Rate-limited to one reflection per user per 30 minutes to contain LLM costs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from app.config import settings
from app import database as _db

logger = logging.getLogger(__name__)

_REFLECTION_COOLDOWN_MINUTES = 30
_MIN_MEMORIES_REQUIRED = 5
_MAX_MEMORY_CHARS = 4000

_REFLECTION_PROMPT = """\
You are maintaining a persistent user model for a personal AI assistant.

{current_section}
Recent memories extracted from the user's conversations:
{memory_block}

Write an updated user model in 4-6 sentences covering:
- Who the user is (role, technical level, domain)
- How they prefer to communicate (concise/detailed, tone, format preferences)
- What they are currently working on or care about most
- Any recurring patterns, strong preferences, or things to avoid

Rules:
- Write in third person ("The user...")
- Be specific and factual — only include what the memories actually show
- If the existing model is mostly accurate, update only what has changed
- Do not invent details not supported by the memories

User model:"""


def _build_memory_block(memories: list[dict]) -> str:
    lines: list[str] = []
    total = 0
    for m in memories:
        line = f"[{m.get('category', 'fact')}] {m.get('content', '')}"
        if total + len(line) > _MAX_MEMORY_CHARS:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


class UserModelManager:
    async def get(self, user_id: Optional[str] = None) -> str:
        """Return the current user model text, or empty string if none exists."""
        if not _db.db_pool:
            return ""
        uid = user_id or "default"
        try:
            async with _db.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT model_text FROM user_model WHERE user_id = $1", uid
                )
            return str(row["model_text"]) if row else ""
        except Exception as e:
            logger.debug("user_model fetch failed: %s", e)
            return ""

    async def run_dialectic_reflection(self, user_id: Optional[str] = None) -> None:
        """
        Fetch recent memories, call cheap LLM, upsert updated user model.
        Skips silently if: flag disabled, DB unavailable, not enough memories,
        or a reflection ran for this user within the cooldown window.
        """
        if not getattr(settings, "AGENT_DIALECTIC_REFLECTION", True):
            return
        if not _db.db_pool:
            return
        if not settings.OPENROUTER_API_KEY:
            return

        uid = user_id or "default"

        # ── Rate-limit check ──────────────────────────────────────────────────
        try:
            async with _db.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT updated_at FROM user_model WHERE user_id = $1", uid
                )
            if row and row["updated_at"]:
                age = datetime.now(UTC) - row["updated_at"].replace(tzinfo=UTC)
                if age < timedelta(minutes=_REFLECTION_COOLDOWN_MINUTES):
                    logger.debug(
                        "user_model reflection skipped — cooldown active for %s", uid
                    )
                    return
        except Exception as e:
            logger.debug("user_model cooldown check failed: %s", e)
            return

        # ── Fetch memories (preference, fact, pattern, insight, observation) ──
        try:
            async with _db.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT category, content FROM memory
                    WHERE user_id = $1
                      AND category IN ('preference', 'fact', 'pattern', 'insight', 'observation')
                    ORDER BY relevance_score DESC, created_at DESC
                    LIMIT 40
                    """,
                    uid,
                )
            memories = [dict(r) for r in rows]
        except Exception as e:
            logger.debug("user_model memory fetch failed: %s", e)
            return

        if len(memories) < _MIN_MEMORIES_REQUIRED:
            logger.debug(
                "user_model reflection skipped — only %d memories for %s",
                len(memories),
                uid,
            )
            return

        # ── Build prompt ──────────────────────────────────────────────────────
        current = await self.get(uid)
        current_section = (
            f"Current user model:\n{current.strip()}\n\n"
            if current.strip()
            else "No existing user model — this is the first synthesis.\n\n"
        )
        prompt = _REFLECTION_PROMPT.format(
            current_section=current_section,
            memory_block=_build_memory_block(memories),
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                base_url=settings.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": settings.SITE_URL,
                    "X-Title": "Personal AI Agent",
                },
            )
            resp = await client.chat.completions.create(
                model=settings.DEFAULT_MODEL_SIMPLE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3,
            )
            model_text = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("user_model LLM call failed: %s", e)
            return

        if not model_text or len(model_text) < 20:
            return

        # ── Upsert ────────────────────────────────────────────────────────────
        try:
            async with _db.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_model (user_id, model_text, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET model_text = EXCLUDED.model_text,
                                  updated_at = EXCLUDED.updated_at
                    """,
                    uid,
                    model_text,
                )
            logger.info("user_model updated for %s (%d chars)", uid, len(model_text))
        except Exception as e:
            logger.warning("user_model upsert failed: %s", e)


user_model_manager = UserModelManager()
