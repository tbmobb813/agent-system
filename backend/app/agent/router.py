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

from openai import AsyncOpenAI

from app.config import settings
from app.agent import cost_learning
from app.utils.pillar_loader import get_pillar_config

logger = logging.getLogger(__name__)


def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


# Router internal tier keys → agent_pillars.yaml llm.model_tiers keys
_ROUTER_TIER_TO_YAML: dict[str, str] = {
    "free": "free",
    "simple": "simple",
    "balanced": "simple",
    "coding": "coding",
    "research": "research",
    "advanced": "advanced",
    "premium": "premium",
    "agent": "agent",
}


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
        settings.DEFAULT_MODEL_AGENT,  # Haiku — primary tool-use model
        settings.DEFAULT_MODEL_RESEARCH,  # Gemini Flash — cheap, supports tool use
        settings.DEFAULT_MODEL_SIMPLE,  # DeepSeek — cheap general fallback
        settings.DEFAULT_MODEL_FREE,  # Free model — last resort (no tool use)
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
            "balanced":       "balanced",
            "coding":         "coding",
            "writing":        "advanced", # Haiku — quality prose matters
            "research":       "research",
            "complex":        "advanced",
            "premium":        "premium",
        }
        tier = tier_map.get(query_type, "balanced")
        model = self.MODELS[tier]["model"]

        # Apply efficiency bias: swap to a cheaper model if it has proven
        # better quality-per-dollar in past runs (reads in-memory cache, no I/O).
        alternatives = [m["model"] for m in self.MODELS.values() if m["model"] != model]
        model = cost_learning.suggest_model(model, alternatives)

        logger.info(f"Routing → {tier} ({model}) for query type: {query_type}")
        return model

    def _classify(self, query: str) -> str:
        """
        Classify query into a routing category.

        Structure: detect modifiers first (brevity, compound), then match
        keywords in priority order, then apply post-processing modifiers
        (length floor, multi-question bump, speed downgrade) before returning.
        """
        q = query.lower().strip()
        words = q.split()
        word_count = len(words)

        # ── Modifier 1: brevity/speed signal ─────────────────────────────
        # User explicitly wants a quick or short answer → downgrade tier.
        wants_brief = any(s in q for s in (
            "quickly", "quick answer", "brief answer", "briefly",
            "in short", "in one sentence", "one sentence answer",
            "tldr", "tl;dr", "short answer", "simple answer",
            "just tell me", "just say", "just give me",
        ))

        # ── Modifier 2: compound / multi-question request ─────────────────
        # Two or more questions, or explicit multi-part phrasing → floor at complex.
        is_multi_part = (
            q.count("?") >= 2
            or any(p in q for p in (
                "and also", "and then", "additionally,", "furthermore,",
                "as well as", "on top of that", "in addition",
                "and finally", "step 1", "step 2",
            ))
        )

        # ── Conversational — always return immediately ────────────────────
        conversational_starts = (
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "how are you", "what's up", "thanks", "thank you", "ok", "okay",
            "sure", "yes", "no", "nice", "great", "awesome", "cool", "lol",
            "are you", "can you help", "do you know",
        )
        if any(q.startswith(w) for w in conversational_starts) or word_count <= 2:
            return "conversational"

        # ── Premium ───────────────────────────────────────────────────────
        premium_keywords = (
            "best possible", "use your best", "use claude sonnet", "use sonnet",
            "most thorough", "spare no detail", "write a complete",
            "professional report", "comprehensive report", "detailed report",
            "full report", "thorough analysis", "full analysis",
            "in-depth analysis", "complete guide", "in-depth guide",
            "cover letter", "business plan", "executive summary",
            "white paper", "literature review",
        )
        if any(kw in q for kw in premium_keywords):
            result = "premium"

        # ── Short definitional / "what is X" — checked before coding ────────
        # Prevents coding keywords (e.g. "python") winning over simple lookups.
        # "what is the best/difference/latest X" — research regardless of length
        elif any(kw in q for kw in (
            "what is the best", "what is the latest", "what is the current",
            "what is the difference", "what is the relationship",
            "what are the best", "what are the main",
        )):
            result = "research"

        # Short definitional "what is X" — simple lookup
        elif (q.startswith("what is ") or (wants_brief and "what is " in q)) and word_count <= 7:
            result = "simple"

        # ── Complex — checked before coding so "analyze this code" → complex ─
        # "framework" omitted — too broad (matches "what framework should I use")
        elif any(kw in q for kw in (
            "analyze", "analyse", "compare", "evaluate", "strategy",
            "strategic", "explain in detail", "pros and cons",
            "trade-off", "tradeoff", "system design", "architecture design",
            "design a system", "step by step", "recommend", "decision",
            "roadmap", "essay", "detailed plan", "make a plan", "write a plan",
            "weigh", "assess", "critique", "structured", "technical design",
        )):
            result = "complex"

        # ── Coding ───────────────────────────────────────────────────────
        elif any(kw in q for kw in (
            "code", "coding", "codebase", "implement", "function", "debug",
            "class", "method", "algorithm", "python", "javascript", "typescript",
            "java ", "rust", "golang", "c++", "c#", " sql ", "bash script",
            "shell script", "write a script", "write me a script", "script to ",
            "write code", "write a function",
            "write a class", "write a program", "program", "refactor",
            "syntax error", "traceback", "stack trace", "exception",
            "dockerfile", "kubernetes", "k8s", "regex", "api endpoint",
            "rest api", "graphql", "unit test", "integration test",
            "npm", "pip install", "import ", "package", "repository",
            "pull request", "git commit", "compile", "linter",
            "type error", "null pointer", "segfault",
        )):
            result = "coding"

        # ── Writing ───────────────────────────────────────────────────────
        # Prose composition: emails, blog posts, essays, creative writing.
        # Routes to advanced (Haiku) — quality prose benefits from a stronger model.
        elif any(kw in q for kw in (
            "write an email", "write a message", "write a letter",
            "draft an email", "draft a message", "draft a letter",
            "compose an email", "compose a message",
            "write a blog", "blog post", "write an article",
            "write an essay", "write a story", "write a poem", "write me a poem",
            "write a short", "write me a short", "write me a ",
            "write a speech", "write a proposal", "write a pitch",
            "write a press release", "write a newsletter",
            "write a description", "write a bio", "write a profile",
            "write a review", "write a summary",
            "write a post", "social media post",
            "rewrite this", "edit this", "improve this writing",
            "proofread", "make this sound", "rephrase",
            "tone of voice", "copywriting", "caption for",
        )):
            result = "writing"

        # ── Research ─────────────────────────────────────────────────────
        elif any(kw in q for kw in (
            "research", "latest", "recent", "current", "news about",
            "what's happening", "what is happening", "tell me about",
            "information about", "information on", "facts about",
            "history of", "overview of", "summarize", "summarise",
            "read this", "review this document", "long article",
            "detailed breakdown", "in depth", "deep dive",
            "comprehensive overview", "market research",
            "explain how", "how does", "how do", "what are the",
            "who are the", "search for", "look up", "find out",
            "investigate", "explore", "trends in", "state of",
            "landscape of", "developments in", "advances in", "updates on",
            "what is the best", "what are the best", "which is better",
            "what should i use", "what would you recommend",
        )):
            result = "research"

        # ── Simple — only when query is short ────────────────────────────
        # Long "what is X" questions are research, not simple lookups.
        elif any(kw in q for kw in (
            "who is", "when did", "where is", "define ", "meaning of",
            "capital of", "how many", "what does", "convert ", "translate",
            "spell ", "calculate", "what year", "what time",
            "how far", "how long", "how much does",
            "what is the price", "what is the cost",
        )) and word_count <= 10:
            result = "simple"

        # "what is X" only simple when short — longer → research
        elif q.startswith("what is ") and word_count <= 6:
            result = "simple"

        else:
            result = "balanced"

        # ── Post-processing: length floor ─────────────────────────────────
        # Long queries are inherently more complex regardless of keywords.
        if word_count > 100 and result in ("balanced", "simple"):
            result = "research"

        # ── Post-processing: multi-question bump ──────────────────────────
        if is_multi_part and result in ("simple", "balanced", "writing"):
            result = "complex"

        # ── Post-processing: speed downgrade ─────────────────────────────
        if wants_brief:
            _SPEED_DOWNGRADE: dict[str, str] = {
                "premium":  "complex",
                "complex":  "balanced",
                "research": "balanced",
                "writing":  "simple",
                "coding":   "simple",
                "advanced": "balanced",
            }
            result = _SPEED_DOWNGRADE.get(result, result)

        return result

    def complexity_mode(self) -> str:
        cfg = get_pillar_config()
        ex = (cfg.get("orchestration") or {}).get("execution") or {}
        return str(ex.get("complexity_threshold") or "keyword").strip().lower()

    async def _classify_query_llm(self, query: str) -> str:
        """Single-label routing; falls back to keyword classifier on any error."""
        rc = (get_pillar_config().get("llm") or {}).get("routing_classifier") or {}
        model = str(rc.get("model") or settings.DEFAULT_MODEL_FREE)
        client = _openrouter_client()
        prompt = (
            "Classify the user message into exactly one category. "
            "Reply with only one word from this list, lowercase: "
            "conversational, simple, coding, writing, research, complex, premium, balanced.\n\n"
            "writing = prose composition (emails, blog posts, essays, creative writing, editing).\n"
            "coding = programming tasks (code, debug, scripts, algorithms).\n"
            "research = information gathering (latest news, explanations, summaries, lookups).\n"
            "complex = multi-step reasoning (analysis, strategy, comparison, system design).\n\n"
            f"Message:\n{query[:4000]}\n\nCategory:"
        )
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=16,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            label = raw.split()[0].rstrip(".,;:") if raw else ""
            allowed = {
                "conversational",
                "simple",
                "coding",
                "writing",
                "research",
                "complex",
                "premium",
                "balanced",
            }
            if label in allowed:
                return label
        except Exception as e:
            logger.debug("LLM routing classifier failed: %s", e)
        return self._classify(query)

    # Models confirmed to support function calling via OpenRouter.
    # Free/meta-llama models are unreliable for tool use and are excluded.
    _TOOL_SAFE_TIERS: set[str] = {
        "simple",
        "balanced",
        "coding",
        "research",
        "writing",
        "advanced",
        "premium",
        "agent",
    }

    def select_for_run(
        self,
        query: str,
        has_tools: bool = False,
        budget_remaining: float = 30.0,
    ) -> str:
        """
        Single entry point for all model selection.
        Orchestrator calls this once — no routing logic should live outside this class.

        When tools are available, routing still follows query complexity — the agent
        tier (Haiku) is only the *minimum floor* for tool-use runs, not a hard override.
        Complex/research/premium queries get a more capable model even with tools.
        """
        # Budget floor always wins.
        if budget_remaining < 2.0:
            logger.warning(
                f"Budget critical (${budget_remaining:.2f}) — forcing free model"
            )
            return self.MODELS["free"]["model"]

        if not has_tools:
            return self.select_model(query, budget_remaining=budget_remaining)

        # Tool run: classify by complexity, then ensure the chosen tier is tool-safe.
        # Note: balanced/simple/conversational use agent (Haiku) not DeepSeek —
        # DeepSeek function calling is inconsistent; reliability > cost for tool runs.
        # Coding also uses agent (Haiku) for tool runs — file_operations and
        # code_execution need reliable function calling, not just code quality.
        query_type = self._classify(query)
        tier_map = {
            "conversational": "agent",
            "simple":         "agent",
            "balanced":       "agent",    # Haiku floor — DeepSeek tool use unreliable
            "coding":         "agent",    # Haiku — file_ops/code_exec need reliability
            "writing":        "advanced", # Haiku — prose with tools (search + write)
            "research":       "research", # Gemini Flash — long context + tool use
            "complex":        "advanced", # Haiku — reliable reasoning + tool use
            "premium":        "premium",  # Sonnet 4 — best quality
        }
        tier = tier_map.get(query_type, "agent")

        # Downgrade if budget is moderate but tier is expensive.
        if budget_remaining < 8.0 and tier == "premium":
            tier = "advanced"
        if tier not in self._TOOL_SAFE_TIERS:
            logger.warning("Tier '%s' is not tool-safe; falling back to agent", tier)
            tier = "agent"

        model = self.MODELS[tier]["model"]
        logger.info(
            f"Tool-run routing → {tier} ({model}) for query type: {query_type}, "
            f"budget_remaining=${budget_remaining:.2f}"
        )
        return model

    def is_complex(self, query: str) -> bool:
        """Return True if the query warrants a planning pass before execution."""
        return self._classify(query) in ("complex", "research", "writing", "premium")

    def should_plan(
        self, query: str, has_tools: bool, has_history: bool = False
    ) -> bool:
        """
        Decide whether the orchestrator should run a planning pass.

        Planning is useful for multi-step work where tools are available.
        Skip planning for conversation follow-ups to avoid repeated overhead.
        """
        if not has_tools or has_history:
            return False
        return self.is_complex(query)

    async def should_plan_async(
        self, query: str, has_tools: bool, has_history: bool = False
    ) -> bool:
        if not has_tools or has_history:
            return False
        if self.complexity_mode() == "llm_classifier" and settings.OPENROUTER_API_KEY:
            qt = await self._classify_query_llm(query)
            return qt in ("complex", "research")
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
            or (
                q.startswith("can you")
                and any(ref in q for ref in followup_refs)
                and len(q.split()) <= 8
            )
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

    def tier_key_for_model(self, model: str) -> Optional[str]:
        """Return router tier key (e.g. agent, simple) for a concrete model id."""
        for tier_key, meta in self.MODELS.items():
            if meta.get("model") == model:
                return tier_key
        return None

    def sampling_params_for_model(self, model: str) -> dict[str, float]:
        """
        temperature / top_p from agent_pillars.yaml for the tier that owns this model.
        Falls back to sensible defaults if yaml is missing or tier unknown.
        """
        defaults = {"temperature": 0.7, "top_p": 0.9}
        tier = self.tier_key_for_model(model)
        yaml_tier = _ROUTER_TIER_TO_YAML.get(tier or "", "simple")
        cfg = get_pillar_config()
        tiers = (cfg.get("llm") or {}).get("model_tiers") or {}
        spec = tiers.get(yaml_tier) or tiers.get("simple") or {}
        try:
            temperature = float(spec.get("temperature", defaults["temperature"]))
        except (TypeError, ValueError):
            temperature = defaults["temperature"]
        try:
            top_p = float(spec.get("top_p", defaults["top_p"]))
        except (TypeError, ValueError):
            top_p = defaults["top_p"]
        return {"temperature": temperature, "top_p": top_p}

    # Rank used by select_for_confidence — higher = more capable / expensive.
    _TIER_RANK: dict[str, int] = {
        "free": 0, "simple": 1, "balanced": 2,
        "coding": 2, "research": 2, "agent": 3,
        "advanced": 4, "premium": 5,
    }

    def select_for_confidence(
        self,
        confidence: float,
        current_model: str,
        budget_remaining: float = 30.0,
    ) -> str:
        """
        Return an upgraded model when plan confidence is low.
        - confidence < 0.65 → at least advanced tier (Haiku)
        - confidence < 0.45 → premium tier (Sonnet), if budget allows
        No-ops if current model is already at or above the target tier.
        """
        if budget_remaining < 2.0:
            return current_model
        current_tier = self.tier_key_for_model(current_model) or "agent"
        current_rank = self._TIER_RANK.get(current_tier, 3)
        if confidence < 0.45 and budget_remaining >= 5.0:
            target_tier, target_rank = "premium", self._TIER_RANK["premium"]
        elif confidence < 0.65:
            target_tier, target_rank = "advanced", self._TIER_RANK["advanced"]
        else:
            return current_model
        if current_rank >= target_rank:
            return current_model
        return self.MODELS[target_tier]["model"]

    def get_next_fallback(self, current_model: str) -> Optional[str]:
        """Get next model in fallback chain after current fails."""
        try:
            idx = self.FALLBACK_CHAIN.index(current_model)
            if idx + 1 < len(self.FALLBACK_CHAIN):
                return self.FALLBACK_CHAIN[idx + 1]
        except ValueError:
            return self.FALLBACK_CHAIN[0]
        return None
