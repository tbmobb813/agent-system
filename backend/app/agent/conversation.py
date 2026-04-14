"""
Conversation Manager — persists and retrieves multi-turn message history.

Each conversation is a thread of user/assistant messages stored in Supabase.
The orchestrator loads prior messages before each LLM call so the model has
full context, and saves the new turn after each response.

Token budget: we load at most MAX_HISTORY_TURNS turns (oldest dropped first)
to avoid blowing the context window.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional

from app import database as _db

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 10   # pairs (user + assistant) to load
DEFAULT_USER      = "default"


class ConversationManager:

    # ── Create / resume ───────────────────────────────────────────────────────

    async def get_or_create(
        self,
        conversation_id: Optional[str],
        user_id: Optional[str] = None,
    ) -> str:
        """
        Return conversation_id.
        Creates a new conversation row if conversation_id is None or not found.
        """
        if not _db.db_pool:
            return conversation_id or str(uuid.uuid4())

        user_id = user_id or DEFAULT_USER

        if conversation_id:
            exists = await self._exists(conversation_id)
            if exists:
                return conversation_id

        # Create new
        new_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            async with _db.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversations (id, user_id, created_at, updated_at)
                    VALUES ($1, $2, $3, $3)
                    """,
                    new_id, user_id, now,
                )
            logger.info(f"Created conversation {new_id}")
        except Exception as e:
            logger.warning(f"Could not create conversation: {e}")
        return new_id

    async def _exists(self, conversation_id: str) -> bool:
        try:
            async with _db.db_pool.acquire() as conn:
                row = await conn.fetchval(
                    "SELECT id FROM conversations WHERE id = $1",
                    conversation_id,
                )
            return row is not None
        except Exception:
            return False

    # ── Load history ──────────────────────────────────────────────────────────

    async def load_messages(
        self,
        conversation_id: str,
        max_turns: int = MAX_HISTORY_TURNS,
    ) -> list[dict]:
        """
        Return the last `max_turns` turn-pairs as OpenAI-format messages:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        if not _db.db_pool:
            return []
        try:
            async with _db.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT role, content FROM (
                        SELECT role, content, created_at
                        FROM messages
                        WHERE conversation_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2
                    ) sub
                    ORDER BY created_at ASC
                    """,
                    conversation_id,
                    max_turns * 2,   # *2 because each turn = user + assistant
                )
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception as e:
            logger.warning(f"Could not load messages: {e}")
            return []

    # ── Save messages ─────────────────────────────────────────────────────────

    async def save_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        user_tokens: int = 0,
        assistant_tokens: int = 0,
    ) -> None:
        """Save one user+assistant turn and update the conversation timestamp."""
        if not _db.db_pool:
            return
        now = datetime.utcnow()
        try:
            async with _db.db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, tokens, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    [
                        (str(uuid.uuid4()), conversation_id, "user",
                         user_message, user_tokens, now),
                        (str(uuid.uuid4()), conversation_id, "assistant",
                         assistant_message, assistant_tokens, now),
                    ],
                )
                await conn.execute(
                    "UPDATE conversations SET updated_at = $1 WHERE id = $2",
                    now, conversation_id,
                )
            logger.debug(f"Saved turn to conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Could not save turn: {e}")

    # ── List conversations ────────────────────────────────────────────────────

    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        if not _db.db_pool:
            return []
        user_id = user_id or DEFAULT_USER
        try:
            async with _db.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT c.id, c.user_id, c.created_at, c.updated_at,
                           COUNT(m.id) AS message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.user_id = $1 AND c.archived = false
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT $2
                    """,
                    user_id, limit,
                )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Could not list conversations: {e}")
            return []

    # ── Token counting ────────────────────────────────────────────────────────

    async def estimate_tokens(self, conversation_id: str) -> int:
        """
        Estimate total tokens used in this conversation.
        Uses stored token counts where available, falls back to char/4.
        """
        if not _db.db_pool:
            return 0
        try:
            async with _db.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT content, tokens FROM messages WHERE conversation_id = $1",
                    conversation_id,
                )
            total = 0
            for r in rows:
                if r["tokens"]:
                    total += r["tokens"]
                else:
                    total += len(r["content"]) // 4
            return total
        except Exception as e:
            logger.warning(f"Token estimate failed: {e}")
            return 0

    # ── Compaction ────────────────────────────────────────────────────────────

    async def compact(
        self,
        conversation_id: str,
        summary: str,
        keep_recent: int = 5,
    ) -> None:
        """
        Replace old messages with a summary, keeping the most recent `keep_recent` turns.
        Called automatically when context usage exceeds the trigger threshold.
        """
        if not _db.db_pool:
            return
        keep_messages = keep_recent * 2   # user + assistant per turn
        now = datetime.utcnow()
        try:
            async with _db.db_pool.acquire() as conn:
                # Find the cutoff: IDs of messages to keep
                recent_ids = await conn.fetch(
                    """
                    SELECT id FROM messages
                    WHERE conversation_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    conversation_id, keep_messages,
                )
                keep_ids = [r["id"] for r in recent_ids]

                # Delete everything older
                if keep_ids:
                    await conn.execute(
                        """
                        DELETE FROM messages
                        WHERE conversation_id = $1
                          AND id != ALL($2::uuid[])
                        """,
                        conversation_id, keep_ids,
                    )
                else:
                    await conn.execute(
                        "DELETE FROM messages WHERE conversation_id = $1",
                        conversation_id,
                    )

                # Insert summary as an assistant message — 'system' role mid-history
                # confuses models; assistant role is standard for injected context.
                await conn.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, tokens, created_at)
                    VALUES ($1, $2, 'assistant', $3, $4, $5)
                    """,
                    str(uuid.uuid4()), conversation_id,
                    f"[Summary of earlier conversation]\n{summary}",
                    len(summary) // 4,
                    now,
                )
            logger.info(f"Compacted conversation {conversation_id}, kept {keep_messages} messages")
        except Exception as e:
            logger.warning(f"Compaction failed: {e}")

    async def delete_conversation(self, conversation_id: str) -> bool:
        if not _db.db_pool:
            return False
        try:
            async with _db.db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM conversations WHERE id = $1", conversation_id
                )
            return True
        except Exception as e:
            logger.warning(f"Could not delete conversation: {e}")
            return False


# Module-level singleton
conversation_manager = ConversationManager()
