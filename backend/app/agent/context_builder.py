"""
ContextBuilder — unified context assembly from all retrieval sources.

Coordinates memory (long-term) and document (RAG) retrieval within a shared
token budget so the combined context never exceeds what the LLM can handle.
Each chunk is source-labelled so the model knows where it came from.
"""

import asyncio
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Chars-per-token estimate for budget calculations (conservative)
_CHARS_PER_TOKEN = 4

# How much of the context window to allocate for retrieved context (10%)
_CONTEXT_BUDGET_FRACTION = 0.10


def _token_estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


class ContextBuilder:
    """
    Fetches and merges context from memory and documents into a single
    system-prompt-ready string, respecting a shared character budget.

    Usage:
        ctx = await ContextBuilder().build(query, user_id=user_id)
        system_prompt += f"\\n\\n{ctx}" if ctx else ""
    """

    def __init__(self, max_tokens: Optional[int] = None):
        self._max_tokens = max_tokens

    @property
    def max_chars(self) -> int:
        return int(
            (self._max_tokens or settings.MAX_CONTEXT_TOKENS)
            * _CONTEXT_BUDGET_FRACTION
            * _CHARS_PER_TOKEN
        )

    async def build(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_limit: int = 4,
        doc_limit: int = 4,
    ) -> str:
        """
        Retrieve from all sources in parallel and merge into a single block.
        Returns empty string if nothing relevant found.
        """
        from app.agent.memory import memory_manager
        from app.agent.documents import search_documents

        memories, doc_chunks = await asyncio.gather(
            memory_manager.search(query, user_id=user_id, limit=memory_limit),
            search_documents(query, user_id=user_id, limit=doc_limit),
        )

        sections: list[str] = []
        budget = self.max_chars

        # ── Memory ────────────────────────────────────────────────────────────
        if memories:
            mem_lines = ["[Memory — past interactions]"]
            for m in memories:
                snippet = m["content"]
                if len(snippet) > budget:
                    snippet = snippet[:budget]
                mem_lines.append(f"• [{m['category']}] {snippet}")
                budget -= len(snippet)
                if budget <= 0:
                    break
            sections.append("\n".join(mem_lines))

        # ── Documents ─────────────────────────────────────────────────────────
        if doc_chunks and budget > 0:
            doc_lines = ["[Documents — uploaded files]"]
            for chunk in doc_chunks:
                header = f"[{chunk['filename']} · chunk {chunk['chunk_index']}]"
                snippet = chunk["content"]
                available = budget - len(header) - 1
                if available <= 0:
                    break
                if len(snippet) > available:
                    snippet = snippet[:available]
                doc_lines.append(f"{header}\n{snippet}")
                budget -= len(header) + len(snippet) + 1
                if budget <= 0:
                    break
            sections.append("\n".join(doc_lines))

        if not sections:
            return ""

        return "\n\n".join(sections)

    def has_docs(self, doc_chunks: list) -> bool:
        return bool(doc_chunks)


# Module-level singleton
context_builder = ContextBuilder()
