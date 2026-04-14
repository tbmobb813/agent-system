"""
Configuration and cost tracking for the personal AI agent system.
Enforces $30/month budget and tracks spending per model.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from datetime import datetime, timedelta
import os
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
    OPENAI_API_KEY: str = Field(default="")  # Optional — used only for embeddings (memory search)
    
    # Budget
    OPENROUTER_BUDGET_MONTHLY: float = Field(default=30.0)  # $30/month limit
    BUDGET_ALERT_PERCENT_80: bool = Field(default=True)
    BUDGET_ALERT_PERCENT_95: bool = Field(default=True)
    
    # Database
    DATABASE_URL: str = Field(default="postgresql://localhost/agent_db")
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")
    
    # Security
    API_KEY_PREFIX: str = Field(default="sk-agent-")
    ALLOWED_HOSTS: list[str] = Field(default=["localhost", "127.0.0.1"])
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3003", "http://localhost:8000", "http://167.88.45.213:3003"])
    SITE_URL: str = Field(default="http://localhost:3003")
    
    # Tools
    SEARXNG_URL: str = Field(default="http://localhost:8888")  # Your SearXNG instance URL
    BRAVE_SEARCH_API_KEY: str = Field(default="")             # Brave Search fallback
    E2B_API_KEY: str = Field(default="")
    
    # Master API keys — comma-separated, bypass DB validation (set in .env)
    BACKEND_API_KEY: str = Field(default="sk-agent-local-dev,sk-agent-telegram-bot")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")        # Your personal chat ID for budget alerts
    ALERT_WEBHOOK_URL: str = Field(default="")       # Optional webhook (Slack, Discord, etc.)
    
    # Model routing
    # Free tier — rate-limited but $0, good for casual/simple queries
    DEFAULT_MODEL_FREE: str = Field(default="meta-llama/llama-3.1-8b-instruct:free")
    # Simple/balanced — DeepSeek is excellent quality at $0.14/M input
    DEFAULT_MODEL_SIMPLE: str = Field(default="deepseek/deepseek-chat")
    DEFAULT_MODEL_BALANCED: str = Field(default="deepseek/deepseek-chat")
    # Coding — DeepSeek is one of the best coding models at any price
    DEFAULT_MODEL_CODING: str = Field(default="deepseek/deepseek-chat")
    # Advanced — Haiku for quality tasks; swap to claude-sonnet-4 only when needed
    DEFAULT_MODEL_ADVANCED: str = Field(default="anthropic/claude-3.5-haiku")
    # Premium — best quality, used only for explicit high-effort requests
    DEFAULT_MODEL_PREMIUM: str = Field(default="anthropic/claude-sonnet-4")
    # Research — long context, detailed analysis (Gemini Flash is very cheap)
    DEFAULT_MODEL_RESEARCH: str = Field(default="google/gemini-2.5-flash-preview-04-17")
    # Agent — must reliably support function calling; Haiku is the sweet spot
    DEFAULT_MODEL_AGENT: str = Field(default="anthropic/claude-3.5-haiku")
    
    # Execution limits
    MAX_STREAM_SECONDS: int = Field(default=300)  # Wall-clock timeout for SSE runs

    # Context limits
    MAX_CONTEXT_TOKENS: int = Field(default=128000)
    CONTEXT_TRIGGER_PERCENT: float = Field(default=0.70)
    KEEP_RECENT_TURNS: int = Field(default=5)
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Load settings
settings = Settings()


class CostTracker:
    """
    Tracks API costs and enforces budget limits.
    All costs are tracked in real-time against the $30/month budget.
    """
    
    # Model pricing (in USD per million tokens, updated April 2026)
    MODEL_PRICING = {
        # ── Free tier (OpenRouter free tier — rate limited) ───────────────────
        "meta-llama/llama-3.1-8b-instruct:free": {"input": 0.0,  "output": 0.0},
        "mistralai/mistral-7b-instruct:free":     {"input": 0.0,  "output": 0.0},
        "qwen/qwen-2-7b-instruct:free":           {"input": 0.0,  "output": 0.0},

        # ── Cheap tier ────────────────────────────────────────────────────────
        # DeepSeek — best value, excellent at coding and general tasks
        "deepseek/deepseek-chat":                 {"input": 0.14, "output": 0.28},
        # GPT-4o Mini — reliable OpenAI option if needed
        "openai/gpt-4o-mini":                     {"input": 0.15, "output": 0.60},

        # ── Mid tier ──────────────────────────────────────────────────────────
        # Gemini Flash — best for long context and research
        "google/gemini-2.5-flash":                {"input": 0.075, "output": 0.30},
        "google/gemini-2.5-flash-preview-04-17":  {"input": 0.075, "output": 0.30},
        # Claude Haiku — reliable tool use, quality responses
        "anthropic/claude-3.5-haiku":             {"input": 1.00, "output": 5.00},

        # ── Premium tier ──────────────────────────────────────────────────────
        # Claude Sonnet 4 — best quality, use sparingly
        "anthropic/claude-sonnet-4":              {"input": 3.00, "output": 15.00},
        # Gemini Pro — Google's premium option
        "google/gemini-2.5-pro":                  {"input": 1.50, "output": 6.00},
    }
    
    def __init__(self):
        """Initialize cost tracker."""
        self.db_pool: Optional[asyncpg.Pool] = None
        self.spending_cache = {}
        self.last_call_cost = 0.0
        self.last_model: Optional[str] = None
        self.last_usage: Optional[dict] = None
    
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
        
        self.last_call_cost = total_cost
        self.last_model = model
        self.last_usage = {"input": input_tokens, "output": output_tokens}

        # Store in database
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO cost_tracking (task_id, model, input_tokens, output_tokens, cost)
                VALUES ($1, $2, $3, $4, $5)
            """, task_id, model, input_tokens, output_tokens, total_cost)
        
        # Check budget and fire alerts
        spent_today = await self.get_spent_today()
        try:
            from app.utils.alerts import alert_manager
            await alert_manager.check_and_notify(spent_today, settings.OPENROUTER_BUDGET_MONTHLY)
        except Exception as e:
            logger.warning(f"Budget alert failed: {e}")

        return total_cost
    
    async def get_spent_today(self) -> float:
        """Get total spending from the start of the month."""
        if not self.db_pool:
            return 0.0
        
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COALESCE(SUM(cost), 0) FROM cost_tracking
                WHERE DATE(created_at) >= DATE_TRUNC('month', NOW())
            """)
        
        return float(result or 0.0)
    
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
        spent = await self.get_spent_today()
        spent_daily = await self.get_spent_today_date()
        remaining = settings.OPENROUTER_BUDGET_MONTHLY - spent
        percent = (spent / settings.OPENROUTER_BUDGET_MONTHLY) * 100
        
        return {
            "budget": settings.OPENROUTER_BUDGET_MONTHLY,
            "spent_month": spent,
            "spent_today": spent_daily,
            "remaining": max(0, remaining),
            "percent_used": percent,
            "status": "ok" if remaining > 0 else "exceeded",
            "reset_date": (datetime.now() + timedelta(days=30)).isoformat(),
        }
    
    async def get_last_call_cost(self) -> float:
        """Get cost of the last API call."""
        return self.last_call_cost

    def get_last_model(self) -> Optional[str]:
        """Get the model used in the last tracked call."""
        return self.last_model

    def get_last_usage(self) -> Optional[dict]:
        """Get token counts from the last tracked call."""
        return self.last_usage
    
    def get_model_pricing(self, model: str) -> dict:
        """Get pricing for a specific model."""
        return self.MODEL_PRICING.get(model, {
            "input": 3.00,
            "output": 15.00
        })


# Initialize cost tracker
cost_tracker = CostTracker()
