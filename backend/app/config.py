"""
Configuration and cost tracking for the personal AI agent system.
Enforces $30/month budget and tracks spending per model.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from datetime import datetime, timedelta
import calendar
import time
import logging
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)

    # API Keys
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    OPENAI_API_KEY: str = Field(
        default=""
    )  # Optional — used only for embeddings (memory search)

    # Budget
    OPENROUTER_BUDGET_MONTHLY: float = Field(default=30.0)  # $30/month limit
    BUDGET_ALERT_PERCENT_80: bool = Field(default=True)
    BUDGET_ALERT_PERCENT_95: bool = Field(default=True)

    # Database
    DATABASE_URL: str = Field(default="postgresql://localhost/agent_db")
    # Optional: Redis for durable deferred-task queue (see orchestration.message_queue.provider)
    REDIS_URL: str = Field(default="")
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")

    # Security
    API_KEY_PREFIX: str = Field(default="sk-agent-")
    ALLOWED_HOSTS: list[str] = Field(default=["localhost", "127.0.0.1"])
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:3003",
            "http://localhost:8000",
        ]
    )
    SITE_URL: str = Field(default="http://localhost:3003")
    AGENT_WORKSPACE_DIR: str = Field(default="/tmp/agent-workspace")
    # If true, non-master API keys require a working database even when ENVIRONMENT is not production.
    REQUIRE_DATABASE_API_KEY: bool = Field(default=False)

    # Connectors
    GITHUB_TOKEN: str = Field(
        default=""
    )  # Personal Access Token — https://github.com/settings/tokens

    # Tools
    SEARXNG_URL: str = Field(
        default="http://localhost:8888"
    )  # Your SearXNG instance URL
    BRAVE_SEARCH_API_KEY: str = Field(default="")  # Brave Search fallback
    E2B_API_KEY: str = Field(default="")
    # Comma-separated host suffixes for browser_automation (e.g. wikipedia.org,.github.io). Empty = SSRF checks only.
    BROWSER_AUTOMATION_ALLOWED_HOST_SUFFIXES: str = Field(default="")

    # Master API keys — comma-separated, bypass DB validation.
    # Must be set explicitly via .env — the empty default forces DB validation for every request.
    BACKEND_API_KEY: str = Field(default="")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")  # Your personal chat ID for budget alerts
    ALERT_WEBHOOK_URL: str = Field(
        default=""
    )  # Optional webhook (Slack, Discord, etc.)

    # Model routing — override any of these in .env to swap models without code changes
    # Free tier — $0, rate-limited; Llama 3.3 70B is the best free model on OpenRouter
    DEFAULT_MODEL_FREE: str = Field(default="meta-llama/llama-3.3-70b-instruct:free")
    # Simple — cheap, fast; short factual questions and quick summaries
    DEFAULT_MODEL_SIMPLE: str = Field(default="deepseek/deepseek-chat")
    # Balanced — default for unclassified queries; strong general model
    DEFAULT_MODEL_BALANCED: str = Field(default="deepseek/deepseek-chat")
    # Coding — DeepSeek V3 is top-tier for code at $0.14/M; beats many expensive models
    DEFAULT_MODEL_CODING: str = Field(default="deepseek/deepseek-chat")
    # Research — Gemini 2.5 Flash: 1M context window, cheap, fast; ideal for long docs
    DEFAULT_MODEL_RESEARCH: str = Field(default="google/gemini-2.5-flash")
    # Advanced — Haiku 4.5: newest Haiku, stronger reasoning than 3.5 at similar price
    DEFAULT_MODEL_ADVANCED: str = Field(default="anthropic/claude-haiku-4.5")
    # Premium — Sonnet 4.6: latest and best Sonnet; use for high-stakes requests
    DEFAULT_MODEL_PREMIUM: str = Field(default="anthropic/claude-sonnet-4.6")
    # Agent — primary ReAct/tool-use model; Haiku 4.5 has best-in-class function calling
    DEFAULT_MODEL_AGENT: str = Field(default="anthropic/claude-haiku-4.5")

    # Execution limits
    MAX_STREAM_SECONDS: int = Field(default=300)  # Wall-clock timeout for SSE runs

    # OpenRouter: optional reasoning/thinking token stream (extra_body.reasoning). Billed as output tokens.
    # Examples: "medium", "high", "low". Unset = omit parameter (provider default; many models still stream reasoning when supported).
    OPENROUTER_REASONING_EFFORT: Optional[str] = Field(default=None)
    QUALITY_SCORING_ENABLED: bool = Field(default=False)
    QUALITY_SCORING_SAMPLE_RATE: float = Field(default=0.10)
    QUALITY_SCORING_MODEL: str = Field(default="anthropic/claude-3.5-haiku")

    # Dialectic user modeling
    AGENT_DIALECTIC_REFLECTION: bool = Field(default=True)

    # Context limits
    MAX_CONTEXT_TOKENS: int = Field(default=128000)
    CONTEXT_TRIGGER_PERCENT: float = Field(default=0.70)
    KEEP_RECENT_TURNS: int = Field(default=5)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


# Load settings
settings = Settings()


class CostTracker:
    """
    Tracks API costs and enforces budget limits.
    All costs are tracked in real-time against the $30/month budget.
    """

    # Model pricing (in USD per million tokens, updated May 2026)
    # IDs verified against OpenRouter /api/v1/models — use dot notation (not dashes).
    MODEL_PRICING = {
        # ── Free tier ─────────────────────────────────────────────────────────
        "meta-llama/llama-3.3-70b-instruct:free": {"input": 0.0, "output": 0.0},
        "mistralai/mistral-7b-instruct:free": {"input": 0.0, "output": 0.0},
        "qwen/qwen-2-7b-instruct:free": {"input": 0.0, "output": 0.0},
        # ── Cheap tier ────────────────────────────────────────────────────────
        # DeepSeek V3 — best value; top-tier coding at $0.14/M input
        "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
        # DeepSeek R1 — reasoning model; best for hard algorithmic problems
        "deepseek/deepseek-r1": {"input": 0.55, "output": 2.19},
        # GPT-4o Mini — solid OpenAI option
        "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
        # ── Mid tier ──────────────────────────────────────────────────────────
        # Gemini 2.5 Flash — 1M context, best for research at this price
        "google/gemini-2.5-flash": {"input": 0.075, "output": 0.30},
        # Claude Haiku 4.5 — newest Haiku; best-in-class function calling
        "anthropic/claude-haiku-4.5": {"input": 0.80, "output": 4.00},
        # Claude 3.5 Haiku — previous Haiku (kept for fallback compatibility)
        "anthropic/claude-3.5-haiku": {"input": 1.00, "output": 5.00},
        # ── Premium tier ──────────────────────────────────────────────────────
        # Claude Sonnet 4.6 — latest Sonnet, best overall quality
        "anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
        # Claude Sonnet 4.5 — previous Sonnet
        "anthropic/claude-sonnet-4.5": {"input": 3.00, "output": 15.00},
        # Claude Sonnet 4 — older Sonnet (kept for cost tracking of past runs)
        "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
        # Gemini 2.5 Pro — Google's premium, strong reasoning + long context
        "google/gemini-2.5-pro": {"input": 1.50, "output": 6.00},
    }

    def __init__(self):
        """Initialize cost tracker."""
        self.db_pool: Optional[asyncpg.Pool] = None
        # Monthly-spend TTL cache — avoids a DB aggregate on every request
        self._spent_cache: float = 0.0
        self._spent_cache_ts: float = 0.0
        self._SPENT_CACHE_TTL: float = 15.0  # seconds
        # Per-task call info — keyed by task_id so concurrent runs don't clobber each other
        self._call_info: dict[str, dict] = {}

    async def initialize(self, database_url: str):
        """Initialize database connection pool."""
        self.db_pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
            statement_cache_size=0,
        )
        logger.info("Cost tracker initialized")

    async def close(self):
        """Close database connections."""
        if self.db_pool:
            await self.db_pool.close()

    async def estimate_cost(self, query: str, model: Optional[str] = None) -> float:
        """
        Estimate cost of a query based on input tokens.
        Conservative estimate: ~0.5 output/input ratio.
        """
        model = model or settings.DEFAULT_MODEL_BALANCED

        # Rough token estimate: ~4 chars per token
        estimated_input_tokens = len(query) / 4

        if model not in self.MODEL_PRICING:
            # Default to mid-tier pricing if model unknown
            model = settings.DEFAULT_MODEL_BALANCED

        pricing = self.MODEL_PRICING[model]
        input_cost = (estimated_input_tokens / 1_000_000) * pricing["input"]
        output_cost = (estimated_input_tokens * 0.5 / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    async def track_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str,
    ) -> float:
        """
        Track actual cost of an API call.
        Called after successful LLM response.
        """
        if model not in self.MODEL_PRICING:
            logger.warning(f"Unknown model for pricing: {model}")
            model = settings.DEFAULT_MODEL_BALANCED

        pricing = self.MODEL_PRICING[model]

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        # Store in database
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cost_tracking (task_id, model, input_tokens, output_tokens, cost)
                VALUES ($1, $2, $3, $4, $5)
            """,
                task_id,
                model,
                input_tokens,
                output_tokens,
                total_cost,
            )

        # Store per-task so concurrent runs don't clobber each other
        self._call_info[task_id] = {
            "cost": total_cost,
            "model": model,
            "usage": {"input": input_tokens, "output": output_tokens},
        }

        # Invalidate the spend cache so the next read reflects this call
        self._spent_cache_ts = 0.0

        # Check budget and fire alerts
        spent_month = await self.get_spent_month()
        try:
            from app.utils.alerts import alert_manager

            await alert_manager.check_and_notify(
                spent_month, settings.OPENROUTER_BUDGET_MONTHLY
            )
        except Exception as e:
            logger.warning(f"Budget alert failed: {e}")

        return total_cost

    async def get_spent_month(self) -> float:
        """Get total spending from the start of the month (cached for 15s)."""
        if not self.db_pool:
            return 0.0

        now = time.monotonic()
        if now - self._spent_cache_ts < self._SPENT_CACHE_TTL:
            return self._spent_cache

        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COALESCE(SUM(cost), 0) FROM cost_tracking
                WHERE DATE(created_at) >= DATE_TRUNC('month', NOW())
            """)

        self._spent_cache = float(result or 0.0)
        self._spent_cache_ts = now
        return self._spent_cache

    async def get_spent_today(self) -> float:
        """Compatibility alias for month-to-date spend. Prefer get_spent_month()."""
        return await self.get_spent_month()

    async def get_spent_today_date(self) -> float:
        """Get spending from today only (for daily alerts)."""
        if not self.db_pool:
            return 0.0

        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COALESCE(SUM(cost), 0) FROM cost_tracking
                WHERE DATE(created_at) = CURRENT_DATE
            """)

        return float(result or 0.0)

    async def get_spent_by_model(self) -> dict:
        """Get spending breakdown by model."""
        if not self.db_pool:
            return {}

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT model, SUM(cost) as total, COUNT(*) as calls
                FROM cost_tracking
                WHERE DATE(created_at) >= DATE_TRUNC('month', NOW())
                GROUP BY model
                ORDER BY total DESC
            """)

        return {r["model"]: {"cost": r["total"], "calls": r["calls"]} for r in rows}

    async def get_status(self) -> dict:
        """Get current budget status."""
        spent = await self.get_spent_month()
        spent_daily = await self.get_spent_today_date()
        remaining = settings.OPENROUTER_BUDGET_MONTHLY - spent
        percent = (spent / settings.OPENROUTER_BUDGET_MONTHLY) * 100

        now = datetime.now()
        last_day = calendar.monthrange(now.year, now.month)[1]
        reset = datetime(now.year, now.month, last_day, 23, 59, 59) + timedelta(
            seconds=1
        )

        return {
            "budget": settings.OPENROUTER_BUDGET_MONTHLY,
            "spent_month": spent,
            "spent_today": spent_daily,
            "remaining": max(0, remaining),
            "percent_used": percent,
            "status": "ok" if remaining > 0 else "exceeded",
            "reset_date": reset.isoformat(),
        }

    def pop_call_info(self, task_id: str) -> dict:
        """Return and remove per-task call info as {cost, model, usage}.

        Falls back to {"cost": 0.0, "model": None, "usage": None} when missing.
        """
        return self._call_info.pop(task_id, {"cost": 0.0, "model": None, "usage": None})

    def _pop_call_info(self, task_id: str) -> dict:
        """Compatibility alias for legacy call sites."""
        return self.pop_call_info(task_id)

    async def get_last_call_cost(self, task_id: Optional[str] = None) -> float:
        """Get cost of the last API call for a task (or most recent if no task_id)."""
        if task_id and task_id in self._call_info:
            return self._call_info[task_id]["cost"]
        # Fallback: most recently inserted entry
        return next(reversed(self._call_info.values()), {}).get("cost", 0.0)

    def get_last_model(self, task_id: Optional[str] = None) -> Optional[str]:
        """Get the model used in the last tracked call for a task."""
        if task_id and task_id in self._call_info:
            return self._call_info[task_id]["model"]
        return next(reversed(self._call_info.values()), {}).get("model")

    def get_last_usage(self, task_id: Optional[str] = None) -> Optional[dict]:
        """Get token counts from the last tracked call for a task."""
        if task_id and task_id in self._call_info:
            return self._call_info[task_id]["usage"]
        return next(reversed(self._call_info.values()), {}).get("usage")

    def get_model_pricing(self, model: str) -> dict:
        """Get pricing for a specific model."""
        return self.MODEL_PRICING.get(model, {"input": 3.00, "output": 15.00})


# Initialize cost tracker
cost_tracker = CostTracker()
