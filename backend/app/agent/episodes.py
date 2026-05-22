"""
Episode logging — persists every agent run to the `episodes` table.

Called fire-and-forget from the orchestrator at both the success and failure
exit points. Never raises; all errors are logged at DEBUG level so a logging
failure cannot surface to the user.

Embeddings are generated after the row is inserted so the INSERT is never
blocked on an OpenAI round-trip. If the embedding call fails (no API key,
quota, etc.) the episode is still stored — it just won't be returned by
semantic search, only by temporal/filter queries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app import database as _db

logger = logging.getLogger(__name__)

_embed_client: Optional[AsyncOpenAI] = None


def _get_embed_client() -> AsyncOpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _embed_client


async def _embed(text: str) -> Optional[list[float]]:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        resp = await _get_embed_client().embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.debug("Episode embedding failed: %s", e)
        return None


async def save_episode(
    *,
    task_id: str,
    user_id: Optional[str],
    query: str,
    outcome: str,
    success: bool,
    tools_used: list[str],
    duration_ms: int,
    cost_usd: Optional[float] = None,
) -> Optional[str]:
    """
    Insert an episode row and then generate+store its embedding.
    Returns the new episode UUID, or None on any failure.
    """
    if not _db.db_pool:
        return None

    # Deduplicate tools_used while preserving first-occurrence order.
    seen: set[str] = set()
    unique_tools: list[str] = []
    for t in tools_used:
        if t not in seen:
            seen.add(t)
            unique_tools.append(t)

    try:
        row = await _db.fetchrow(
            """
            INSERT INTO episodes
                (user_id, task_id, query, outcome, success,
                 tools_used, cost_usd, duration_ms)
            VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            user_id,
            task_id,
            query,
            outcome[:4000],
            success,
            unique_tools,
            cost_usd,
            duration_ms,
        )
    except Exception as e:
        logger.debug("Episode insert failed: %s", e)
        return None

    episode_id: str = str(row["id"])

    # Generate and store the embedding without blocking the caller.
    asyncio.create_task(_backfill_embedding(episode_id, query, outcome))

    return episode_id


async def _backfill_embedding(episode_id: str, query: str, outcome: str) -> None:
    """Generate an embedding for the episode and write it back."""
    embedding = await _embed(f"{query} {outcome[:500]}")
    if embedding is None:
        return
    try:
        await _db.execute(
            "UPDATE episodes SET embedding = $1 WHERE id = $2::uuid",
            embedding,
            episode_id,
        )
    except Exception as e:
        logger.debug("Episode embedding update failed: %s", e)
