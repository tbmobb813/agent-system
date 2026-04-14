"""
Memory Manager — saves and retrieves long-term memories for the agent.

Storage:  Supabase `memory` table with pgvector (1536-dim embeddings).
Search:   Semantic (cosine similarity) if OPENAI_API_KEY is set,
          otherwise PostgreSQL full-text search.

Auto-save: after each agent run, the query+response is stored as a
           'context' memory so future queries can reference past work.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.database import db_pool

logger = logging.getLogger(__name__)

DEFAULT_USER = "default"
MAX_MEMORY_CONTENT = 2000   # chars stored per memory
MAX_CONTEXT_CHARS  = 1500   # chars injected into system prompt


# ─────────────────────────────────────────────────────────────────────────────
# Embedding helper
# ─────────────────────────────────────────────────────────────────────────────

async def _embed(text: str) -> Optional[list[float]]:
    """Generate a 1536-dim embedding via OpenAI. Returns None if key not set."""
    if not settings.OPENAI_API_KEY:
        return None
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],   # model limit
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Insight extraction
# ─────────────────────────────────────────────────────────────────────────────

_INSIGHT_PROMPT = """\
You are a memory filter for an AI assistant. Your job is to extract only what \
is worth remembering long-term from a single conversation exchange.

Rules:
- Extract preferences ("user prefers X over Y"), facts ("user works on project Z"), \
or patterns ("user always wants code in Python").
- Be concise — one sentence maximum.
- If the exchange is trivial (greetings, simple factual Q&A with no personal context, \
generic questions), return exactly: NOTHING
- Do NOT return the conversation itself, summaries, or explanations.

Conversation:
Q: {query}
A: {response}

Insight (or NOTHING):"""

_CLASSIFY_KEYWORDS = {
    "prefer": "preference",
    "prefer": "preference",
    "always": "pattern",
    "never": "pattern",
    "usually": "pattern",
    "like": "preference",
    "dislike": "preference",
    "want": "preference",
    "use": "preference",
    "project": "fact",
    "working on": "fact",
    "my ": "fact",
    "i am": "fact",
    "i'm": "fact",
}


async def _extract_insight(query: str, response: str) -> Optional[str]:
    """
    Call the cheap model to extract a single memorable insight.
    Returns None if nothing worth saving.
    """
    if not settings.OPENROUTER_API_KEY:
        return None

    prompt = _INSIGHT_PROMPT.format(
        query=query[:300],
        response=response[:600],
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            default_headers={"HTTP-Referer": "http://localhost:3000", "X-Title": "Personal AI Agent"},
        )
        resp = await client.chat.completions.create(
            model=settings.DEFAULT_MODEL_SIMPLE,   # cheapest tier
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0,
        )
        result = (resp.choices[0].message.content or "").strip()
        if not result or result.upper() == "NOTHING" or len(result) < 8:
            return None
        return result
    except Exception as e:
        logger.debug(f"Insight extraction failed: {e}")
        return None


def _classify_insight(insight: str) -> str:
    """Classify an insight into a memory category based on keywords."""
    lower = insight.lower()
    for keyword, category in _CLASSIFY_KEYWORDS.items():
        if keyword in lower:
            return category
    return "fact"


# ─────────────────────────────────────────────────────────────────────────────
# MemoryManager
# ─────────────────────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Saves and retrieves memories from the `memory` table in Supabase.

    Usage:
        mm = MemoryManager()
        await mm.save("User prefers Python", category="preference", user_id="u1")
        context = await mm.get_context_for_query("write a script", user_id="u1")
    """

    async def save(
        self,
        content: str,
        category: str = "context",
        user_id: Optional[str] = None,
        relevance_score: float = 1.0,
    ) -> Optional[str]:
        """
        Save a memory. Returns the new memory ID or None on failure.

        Categories:
          context    — past query/response pairs (auto-saved)
          preference — user preferences learned over time
          fact       — specific facts the user has told the agent
          pattern    — recurring patterns in user behaviour
        """
        if not db_pool:
            return None

        user_id = user_id or DEFAULT_USER
        content = content[:MAX_MEMORY_CONTENT]
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Generate embedding (may be None if no OPENAI_API_KEY)
        embedding = await _embed(content)

        try:
            async with db_pool.acquire() as conn:
                if embedding:
                    await conn.execute(
                        """
                        INSERT INTO memory
                          (id, user_id, category, content, embedding,
                           created_at, accessed_at, relevance_score)
                        VALUES ($1,$2,$3,$4,$5::vector,$6,$7,$8)
                        """,
                        memory_id, user_id, category, content,
                        str(embedding),   # asyncpg expects text cast for vector
                        now, now, relevance_score,
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO memory
                          (id, user_id, category, content,
                           created_at, accessed_at, relevance_score)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        """,
                        memory_id, user_id, category, content,
                        now, now, relevance_score,
                    )
            logger.info(f"Saved memory {memory_id} ({category}) for user {user_id}")
            return memory_id
        except Exception as e:
            logger.warning(f"Failed to save memory: {e}")
            return None

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Find memories relevant to the query.
        Uses pgvector cosine similarity if embeddings are available,
        otherwise falls back to PostgreSQL full-text search.
        """
        if not db_pool:
            return []

        user_id = user_id or DEFAULT_USER

        # ── Semantic search ──────────────────────────────────────────
        query_embedding = await _embed(query)
        if query_embedding:
            return await self._vector_search(query_embedding, user_id, limit, category)

        # ── Full-text fallback ───────────────────────────────────────
        return await self._fulltext_search(query, user_id, limit, category)

    async def _vector_search(
        self,
        embedding: list[float],
        user_id: str,
        limit: int,
        category: Optional[str],
    ) -> list[dict]:
        try:
            async with db_pool.acquire() as conn:
                cat_filter = "AND category = $4" if category else ""
                params = [str(embedding), user_id, limit]
                if category:
                    params.append(category)

                rows = await conn.fetch(
                    f"""
                    SELECT id, category, content, relevance_score,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM memory
                    WHERE user_id = $2
                      AND embedding IS NOT NULL
                      {cat_filter}
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    *params,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    async def _fulltext_search(
        self,
        query: str,
        user_id: str,
        limit: int,
        category: Optional[str],
    ) -> list[dict]:
        try:
            async with db_pool.acquire() as conn:
                cat_filter = "AND category = $3" if category else ""
                params = [user_id, query]
                if category:
                    params.append(category)
                params.append(limit)

                rows = await conn.fetch(
                    f"""
                    SELECT id, category, content, relevance_score,
                           ts_rank(to_tsvector('english', content),
                                   plainto_tsquery('english', $2)) AS similarity
                    FROM memory
                    WHERE user_id = $1
                      AND to_tsvector('english', content)
                          @@ plainto_tsquery('english', $2)
                      {cat_filter}
                    ORDER BY similarity DESC
                    LIMIT ${len(params)}
                    """,
                    *params,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Full-text search failed: {e}")
            return []

    async def get_recent(
        self,
        user_id: Optional[str] = None,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve the most recent memories."""
        if not db_pool:
            return []
        user_id = user_id or DEFAULT_USER
        try:
            async with db_pool.acquire() as conn:
                cat_filter = "AND category = $3" if category else ""
                params = [user_id, limit]
                if category:
                    params.insert(1, category)
                    params = [user_id, category, limit]

                rows = await conn.fetch(
                    f"""
                    SELECT id, category, content, relevance_score, created_at
                    FROM memory
                    WHERE user_id = $1 {cat_filter}
                    ORDER BY created_at DESC
                    LIMIT ${len(params)}
                    """,
                    *params,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch recent memories: {e}")
            return []

    async def get_context_for_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 4,
    ) -> str:
        """
        Search for relevant memories and format them as a context string
        ready to inject into the LLM system prompt.
        Returns an empty string if no relevant memories found.
        """
        memories = await self.search(query, user_id=user_id, limit=limit)
        if not memories:
            return ""

        lines = ["Relevant context from past interactions:"]
        total = 0
        for m in memories:
            snippet = m["content"]
            if total + len(snippet) > MAX_CONTEXT_CHARS:
                snippet = snippet[:MAX_CONTEXT_CHARS - total]
            lines.append(f"- [{m['category']}] {snippet}")
            total += len(snippet)
            if total >= MAX_CONTEXT_CHARS:
                break

        return "\n".join(lines)

    async def save_interaction(
        self,
        query: str,
        response: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Extract meaningful insights from the conversation using a cheap LLM,
        then save only what's worth remembering. Skips trivial exchanges.
        """
        insight = await _extract_insight(query, response)
        if not insight:
            logger.debug("No insight worth saving from this interaction")
            return

        # Classify into the right category
        category = _classify_insight(insight)
        await self.save(insight, category=category, user_id=user_id)
        logger.info(f"Saved insight [{category}]: {insight[:80]}")

    async def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        if not db_pool:
            return False
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM memory WHERE id = $1", memory_id)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete memory {memory_id}: {e}")
            return False


# Module-level singleton
memory_manager = MemoryManager()
