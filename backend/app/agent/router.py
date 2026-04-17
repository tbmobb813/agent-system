"""
Model Router - Selects the optimal model based on query complexity.

Routing priority:
  1. Free models for simple conversational queries (no tool use)
  2. DeepSeek for most tasks — excellent quality, very cheap ($0.14/M)
  3. Claude Haiku for tool use and advanced tasks — reliable function calling
  4. Claude Sonnet only when explicitly needed (complex reasoning, long docs)

Tool use always routes to the agent tier (Haiku) — free/cheap models are
unreliable for function-calling format.
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class ModelRouter:
    MODELS = {
        "free": {
            "model": settings.DEFAULT_MODEL_FREE,
            "cost_tier": "free",
            "description": "Casual chat, greetings, quick facts",
        },
        "simple": {
            "model": settings.DEFAULT_MODEL_SIMPLE,
            "cost_tier": "cheap",
            "description": "Short questions, summaries, translations",
        },
        "balanced": {
            "model": settings.DEFAULT_MODEL_BALANCED,
            "cost_tier": "cheap",
            "description": "General queries, research, explanations",
        },
        "coding": {
            "model": settings.DEFAULT_MODEL_CODING,
            "cost_tier": "cheap",
            "description": "Code generation, debugging, refactoring",
        },
        "research": {
            "model": settings.DEFAULT_MODEL_RESEARCH,
            "cost_tier": "cheap",
            "description": "Long-context research, detailed analysis (Gemini Flash)",
        },
        "advanced": {
            "model": settings.DEFAULT_MODEL_ADVANCED,
            "cost_tier": "medium",
            "description": "Complex reasoning, quality writing (Claude Haiku)",
        },
        "premium": {
            "model": settings.DEFAULT_MODEL_PREMIUM,
            "cost_tier": "expensive",
            "description": "Best quality — Claude Sonnet 4, use sparingly",
        },
        "agent": {
            "model": settings.DEFAULT_MODEL_AGENT,
            "cost_tier": "medium",
            "description": "Tool use / ReAct loop — reliable function calling",
        },
    }

    # Fallback chain: if a model fails, try the next one
    FALLBACK_CHAIN = [
        settings.DEFAULT_MODEL_AGENT,    # Haiku — primary tool-use model
        settings.DEFAULT_MODEL_RESEARCH, # Gemini Flash — cheap, supports tool use
        settings.DEFAULT_MODEL_SIMPLE,   # DeepSeek — cheap general fallback
        settings.DEFAULT_MODEL_FREE,     # Free model — last resort (no tool use)
    ]

    def select_model(
        self,
        query: str,
        context: Optional[str] = None,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
        budget_remaining: float = 30.0,
    ) -> str:
        """
        Select the best model for a query with no tool use.

        Strategy:
        - Conversational / very simple → free model
        - Coding → DeepSeek (best value for code)
        - Complex reasoning → Haiku
        - Default → DeepSeek (cheap and capable)
        """
        # Budget protection: force cheapest if nearly depleted
        if budget_remaining < 2.0:
            logger.warning(f"Budget low (${budget_remaining:.2f}) — forcing free model")
            return self.MODELS["free"]["model"]
        if budget_remaining < 8.0:
            logger.info(f"Budget moderate (${budget_remaining:.2f}) — using DeepSeek")
            return self.MODELS["simple"]["model"]

        if prefer_speed:
            return self.MODELS["free"]["model"]
        if prefer_quality:
            return self.MODELS["premium"]["model"]

        query_type = self._classify(query)

        tier_map = {
            "conversational": "free",
            "simple":         "simple",
            "coding":         "coding",
            "research":       "research",
            "complex":        "advanced",
            "premium":        "premium",
            "balanced":       "balanced",
        }
        tier = tier_map.get(query_type, "balanced")
        model = self.MODELS[tier]["model"]

        logger.info(f"Routing → {tier} ({model}) for query type: {query_type}")
        return model

    def _classify(self, query: str) -> str:
        """Classify query into a routing category."""
        q = query.lower().strip()

        # Very short / conversational
        conversational = [
            "hi", "hello", "hey", "good morning", "good afternoon",
            "good evening", "how are you", "what's up", "thanks",
            "thank you", "ok", "okay", "sure", "yes", "no",
        ]
        if any(q.startswith(w) for w in conversational) or len(q.split()) <= 4:
            return "conversational"

        # Premium — explicit quality signals or long-form serious work
        premium_keywords = [
            "best possible", "use your best", "use claude sonnet",
            "use sonnet", "most thorough", "spare no detail",
            "write a full", "write a complete", "professional report",
            "cover letter", "business plan", "legal", "medical",
        ]
        if any(kw in q for kw in premium_keywords):
            return "premium"

        # Research / long-context (Gemini Flash excels here)
        research_keywords = [
            "research", "summarize this", "summarise this",
            "read this", "review this document", "long article",
            "detailed breakdown", "in depth", "deep dive",
            "comprehensive overview", "market research",
        ]
        if any(kw in q for kw in research_keywords):
            return "research"

        # Coding
        coding_keywords = [
            "code", "write", "implement", "function", "debug", "fix",
            "class", "method", "algorithm", "python", "javascript",
            "typescript", "java", "rust", "golang", "sql", "script",
            "program", "refactor", "bug", "error", "exception",
            "dockerfile", "regex", "api", "endpoint", "test",
        ]
        if any(kw in q for kw in coding_keywords):
            return "coding"

        # Complex reasoning
        complex_keywords = [
            "analyze", "analyse", "compare", "evaluate", "strategy",
            "explain in detail", "pros and cons", "trade-off",
            "architecture", "design", "step by step", "breakdown",
            "essay", "report", "plan",
        ]
        if any(kw in q for kw in complex_keywords):
            return "complex"

        # Simple lookup / facts
        simple_keywords = [
            "what is", "who is", "when did", "where is", "define",
            "meaning of", "capital of", "how many", "what does",
            "convert", "translate", "spell", "calculate",
        ]
        if any(kw in q for kw in simple_keywords):
            return "simple"

        return "balanced"

    def select_for_run(
        self,
        query: str,
        has_tools: bool = False,
        budget_remaining: float = 30.0,
    ) -> str:
        """
        Single entry point for all model selection.
        Orchestrator calls this once — no routing logic should live outside this class.
        """
        if has_tools:
            # Tool/ReAct runs always use the agent tier (reliable function calling).
            # Still respect budget floor — fall back to cheapest if nearly depleted.
            if budget_remaining < 2.0:
                logger.warning(f"Budget critical (${budget_remaining:.2f}) — forcing free model for tool run")
                return self.MODELS["free"]["model"]
            return self.MODELS["agent"]["model"]
        return self.select_model(query, budget_remaining=budget_remaining)

    def is_complex(self, query: str) -> bool:
        """Return True if the query warrants a planning pass before execution."""
        return self._classify(query) in ("complex", "research")

    def should_plan(self, query: str, has_tools: bool, has_history: bool = False) -> bool:
        """
        Decide whether the orchestrator should run a planning pass.

        Planning is useful for multi-step work where tools are available.
        Skip planning for conversation follow-ups to avoid repeated overhead.
        """
        if not has_tools or has_history:
            return False
        return self.is_complex(query)

    def is_worth_remembering(self, query: str) -> bool:
        """Return True if the query is substantive enough to warrant memory extraction.
        Skips free/cheap tiers (conversational, simple) to avoid wasting tokens on
        throwaway exchanges like greetings or one-line factual lookups.
        """
        return self._classify(query) not in ("conversational", "simple")

    def should_remember(
        self,
        query: str,
        has_history: bool = False,
        response: Optional[str] = None,
    ) -> bool:
        """
        Decide whether to run memory extraction for a completed turn.

        Keep extraction for substantive prompts, but skip low-value follow-up
        edits in existing conversations (for example: "make that shorter").
        """
        if not self.is_worth_remembering(query):
            return False

        if not has_history:
            return True

        q = query.lower().strip()
        followup_prefixes = (
            "can you ",
            "could you ",
            "please ",
            "make it ",
            "make that ",
            "shorten ",
            "reword ",
            "rewrite ",
            "tweak ",
            "adjust ",
            "fix that",
            "change that",
            "update that",
            "same for ",
            "now ",
            "also ",
        )
        followup_refs = (
            " that",
            " this",
            " it",
            " above",
            " previous",
            " earlier",
        )
        transactional_edits = (
            "make it shorter",
            "make that shorter",
            "shorten that",
            "shorten this",
            "reword that",
            "rewrite that",
            "tweak that",
            "adjust that",
            "fix that",
            "change that",
            "update that",
            "same for that",
            "same for this",
        )

        if len(q.split()) <= 12 and (
            any(q.startswith(prefix) for prefix in followup_prefixes)
            or any(phrase in q for phrase in transactional_edits)
            or (q.startswith("can you") and any(ref in q for ref in followup_refs) and len(q.split()) <= 8)
        ):
            return False

        if response:
            r = response.lower().strip()
            brief_ack_prefixes = (
                "updated",
                "revised",
                "done",
                "sure",
                "here you go",
            )
            if (
                len(q.split()) <= 10
                and len(r.split()) <= 20
                and any(r.startswith(prefix) for prefix in brief_ack_prefixes)
            ):
                return False

        return True

    def get_available_models(self) -> dict:
        return self.MODELS

    def get_next_fallback(self, current_model: str) -> Optional[str]:
        """Get next model in fallback chain after current fails."""
        try:
            idx = self.FALLBACK_CHAIN.index(current_model)
            if idx + 1 < len(self.FALLBACK_CHAIN):
                return self.FALLBACK_CHAIN[idx + 1]
        except ValueError:
            return self.FALLBACK_CHAIN[0]
        return None
