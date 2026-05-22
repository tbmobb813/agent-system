"""
Skill Extractor — LLM-authored skill generation from completed episodes.

Background job that scans recent qualifying episodes and extracts reusable
skill knowledge into the authored_skills table. Skills are injected into the
system prompt at runtime so the agent doesn't re-solve the same problem.

Qualifying criteria for an episode:
  - success = TRUE
  - duration_ms >= MIN_DURATION_MS  (complex enough to be worth capturing)
  - at least MIN_TOOLS_USED distinct tools were used
  - authored_skill_id IS NULL       (not already processed)

Throttled to REFRESH_INTERVAL_MINUTES — safe to fire on every agent run.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app import database as _db
from app.agent.episodes import _embed

logger = logging.getLogger(__name__)

MIN_DURATION_MS = 8_000
MIN_TOOLS_USED = 2
DEDUP_SIMILARITY = 0.85
LOOKBACK_HOURS = 24
REFRESH_INTERVAL_MINUTES = 30

_LAST_RUN: Optional[datetime] = None

_EXTRACTION_PROMPT = """\
Given this completed agent task, extract a reusable skill as JSON.

TASK: {query}
TOOLS USED: {tools}
OUTCOME: {outcome}

Return ONLY a JSON object with these exact keys:
{{
    "name": "Short skill name (5-8 words)",
    "pattern": "The type of problem this solves (1-2 sentences)",
    "solution": "The approach that worked — key steps, patterns, or observations (3-6 sentences)",
    "preconditions": ["when to apply this skill"],
    "gotchas": ["what can go wrong or trip you up"]
}}

Be specific. If a particular tool sequence or query pattern worked, name it.\
"""


def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": "Personal AI Agent",
        },
    )


async def _call_extraction_llm(episode: dict) -> Optional[dict]:
    """
    Call the cheap model to extract structured skill knowledge from one episode.
    Returns a parsed dict on success, None on any failure.
    """
    tools_str = ", ".join(episode.get("tools_used") or []) or "none"
    outcome = (episode.get("outcome") or "")[:600]
    prompt = _EXTRACTION_PROMPT.format(
        query=episode["query"],
        tools=tools_str,
        outcome=outcome,
    )
    try:
        resp = await _openrouter_client().chat.completions.create(
            model=settings.DEFAULT_MODEL_SIMPLE,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        logger.debug("Skill extraction LLM call failed: %s", e)
        return None


async def _find_similar_skill(
    user_id: Optional[str], embedding: list[float]
) -> Optional[dict]:
    """
    Return the closest authored_skill if its cosine similarity exceeds
    DEDUP_SIMILARITY, else None. Uses pgvector directly via pool.acquire()
    following the same pattern as memory._vector_search.
    """
    if not _db.db_pool:
        return None
    try:
        async with _db.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, use_count, success_count,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM authored_skills
                WHERE user_id IS NOT DISTINCT FROM $2
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 1
                """,
                str(embedding),
                user_id,
            )
        if rows and float(rows[0]["similarity"]) >= DEDUP_SIMILARITY:
            return dict(rows[0])
    except Exception as e:
        logger.debug("Skill similarity search failed: %s", e)
    return None


async def maybe_extract_skill(episode: dict) -> Optional[str]:
    """
    Attempt to extract or update a skill from a single episode dict.

    Returns the authored_skill UUID (str) that was created or updated,
    or None if extraction was skipped or failed. Never raises.
    """
    if not _db.db_pool:
        return None
    if episode.get("authored_skill_id"):
        return str(episode["authored_skill_id"])

    # 1. Extract structured skill knowledge via LLM
    skill_data = await _call_extraction_llm(episode)
    if not skill_data or not skill_data.get("name") or not skill_data.get("pattern"):
        logger.debug(
            "Skill extraction skipped — empty result for episode %s", episode.get("id")
        )
        return None

    # 2. Embed the pattern for dedup check
    pattern_embedding = await _embed(skill_data["pattern"])

    episode_id = str(episode["id"])
    user_id = episode.get("user_id")

    # 3. Dedup: update existing skill if similar enough
    existing = None
    if pattern_embedding:
        existing = await _find_similar_skill(user_id, pattern_embedding)

    if existing:
        skill_id = str(existing["id"])
        try:
            await _db.execute(
                """
                UPDATE authored_skills
                SET use_count          = use_count + 1,
                    success_count      = success_count + 1,
                    source_episode_ids = array_append(source_episode_ids, $1::uuid),
                    updated_at         = NOW()
                WHERE id = $2::uuid
                """,
                episode_id,
                skill_id,
            )
        except Exception as e:
            logger.debug("Skill use_count update failed: %s", e)
            return None
    else:
        # 4. Insert new skill row (without embedding — backfilled below)
        preconditions = skill_data.get("preconditions") or []
        gotchas = skill_data.get("gotchas") or []
        if not isinstance(preconditions, list):
            preconditions = []
        if not isinstance(gotchas, list):
            gotchas = []
        try:
            row = await _db.fetchrow(
                """
                INSERT INTO authored_skills
                    (user_id, name, pattern, solution,
                     preconditions, gotchas, source_episode_ids,
                     use_count, success_count)
                VALUES ($1, $2, $3, $4, $5, $6, ARRAY[$7::uuid], 1, 1)
                RETURNING id
                """,
                user_id,
                skill_data["name"][:200],
                skill_data["pattern"][:1000],
                skill_data.get("solution", "")[:4000],
                preconditions,
                gotchas,
                episode_id,
            )
            skill_id = str(row["id"])
        except Exception as e:
            logger.debug("Authored skill insert failed: %s", e)
            return None

        # 5. Backfill embedding on new skills (separate UPDATE, no None::vector issue)
        if pattern_embedding:
            try:
                async with _db.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE authored_skills SET embedding = $1::vector WHERE id = $2::uuid",
                        str(pattern_embedding),
                        skill_id,
                    )
            except Exception as e:
                logger.debug("Authored skill embedding backfill failed: %s", e)

    # 6. Link episode back to the skill
    try:
        await _db.execute(
            "UPDATE episodes SET authored_skill_id = $1::uuid WHERE id = $2::uuid",
            skill_id,
            episode_id,
        )
    except Exception as e:
        logger.debug("Episode authored_skill_id link failed: %s", e)

    logger.info(
        "Skill %s '%s' for episode %s",
        "updated" if existing else "created",
        skill_data["name"],
        episode_id,
    )
    return skill_id


async def search_authored_skills(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 3,
) -> list[dict]:
    """
    Return the most relevant authored skills for a query.
    Uses pgvector cosine similarity when an embedding is available,
    falls back to PostgreSQL full-text search otherwise.
    Returns an empty list on any failure.
    """
    if not _db.db_pool:
        return []

    query_embedding = await _embed(query)

    if query_embedding:
        try:
            async with _db.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT name, pattern, solution, preconditions, gotchas,
                           use_count, success_count
                    FROM authored_skills
                    WHERE ($1::text IS NULL OR user_id = $1)
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    user_id,
                    str(query_embedding),
                    limit,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug("Authored skills vector search failed: %s", e)

    # Full-text fallback
    try:
        rows = await _db.fetch(
            """
            SELECT name, pattern, solution, preconditions, gotchas,
                   use_count, success_count
            FROM authored_skills
            WHERE ($1::text IS NULL OR user_id = $1)
              AND to_tsvector('english', name || ' ' || pattern)
                  @@ plainto_tsquery('english', $2)
            ORDER BY use_count DESC
            LIMIT $3
            """,
            user_id,
            query,
            limit,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("Authored skills fulltext search failed: %s", e)
        return []


async def extract_skills_from_recent_episodes(
    user_id: Optional[str] = None,
    lookback_hours: int = LOOKBACK_HOURS,
) -> int:
    """
    Scan recent qualifying episodes and extract skills from each.
    Throttled to REFRESH_INTERVAL_MINUTES — safe to call on every agent run.
    Returns the number of skills created or updated (0 if throttled).
    """
    global _LAST_RUN
    if _LAST_RUN and datetime.now(UTC) - _LAST_RUN < timedelta(
        minutes=REFRESH_INTERVAL_MINUTES
    ):
        return 0
    if not _db.db_pool:
        return 0

    try:
        rows = await _db.fetch(
            """
            SELECT id, user_id, query, outcome, tools_used,
                   duration_ms, authored_skill_id
            FROM episodes
            WHERE success = TRUE
              AND duration_ms >= $1
              AND array_length(tools_used, 1) >= $2
              AND authored_skill_id IS NULL
              AND created_at > NOW() - $3::interval
              AND ($4::text IS NULL OR user_id = $4)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            MIN_DURATION_MS,
            MIN_TOOLS_USED,
            timedelta(hours=lookback_hours),
            user_id,
        )
    except Exception as e:
        logger.debug("Episode fetch for skill extraction failed: %s", e)
        return 0

    _LAST_RUN = datetime.now(UTC)

    if not rows:
        return 0

    count = 0
    for row in rows:
        skill_id = await maybe_extract_skill(dict(row))
        if skill_id:
            count += 1

    if count:
        logger.info(
            "Skill extraction complete: %d/%d episodes yielded a skill",
            count,
            len(rows),
        )
    return count
