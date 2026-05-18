"""
Telegram Bot - Access your AI agent from Telegram.
"""

import os
import logging
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Load from local .env first, then fall back to backend .env
_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_dir, ".env"))
load_dotenv(os.path.join(_dir, "..", "backend", ".env"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
# Avoid logging full Telegram API URLs (they contain the bot token path segment).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# If BACKEND_API_URL is set, use it strictly. Otherwise, try sane defaults for
# both local runs and docker-network runs.
_backend_env = (os.getenv("BACKEND_API_URL") or "").strip()
BACKEND_URLS = (
    [_backend_env] if _backend_env else ["http://localhost:8000", "http://backend:8000"]
)
# Prefer a dedicated bot key, but fall back to the backend master key for local setups.
API_KEY = os.getenv("TELEGRAM_BOT_API_KEY") or os.getenv("BACKEND_API_KEY", "")


def _parse_chat_id(raw_value: str) -> int:
    value = (raw_value or "").strip().strip("\"'")
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        logger.error("Invalid TELEGRAM_CHAT_ID value: %r", raw_value)
        return 0


_ALLOWED_CHAT_ID = _parse_chat_id(os.getenv("TELEGRAM_CHAT_ID", "0"))

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Per-chat conversation tracking: {chat_id: conversation_id}
_chat_conversations: dict[int, str] = {}


def _is_authorized(update: Update) -> bool:
    """Return True only if the message comes from the configured chat ID."""
    if not _ALLOWED_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — rejecting all messages")
        return False
    chat_id = update.effective_chat.id
    if chat_id != _ALLOWED_CHAT_ID:
        logger.warning(
            "Unauthorized chat_id %s (expected %s) — ignoring message",
            chat_id,
            _ALLOWED_CHAT_ID,
        )
        return False
    return True


# ============================================================================
# Helpers
# ============================================================================


def _truncate(text: str, limit: int = 4000) -> str:
    """Truncate to Telegram's 4096-char message limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…\n\n_(response truncated)_"


async def _call_backend(method: str, path: str, **kwargs) -> dict | None:
    """Make a request to the backend. Returns parsed JSON or None on error."""
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=3.0)) as client:
        fn = getattr(client, method)
        for base in BACKEND_URLS:
            try:
                resp = await fn(f"{base}{path}", headers=HEADERS, **kwargs)
                if resp.status_code == 200:
                    return resp.json()
                logger.error(
                    "Backend %s %s via %s → %s: %s",
                    method.upper(),
                    path,
                    base,
                    resp.status_code,
                    resp.text,
                )
                return None
            except Exception as e:
                last_error = e
                continue

    if last_error:
        logger.error(
            "Backend request failed for %s across %s: %s",
            path,
            BACKEND_URLS,
            last_error,
        )
    else:
        logger.error("Backend request failed for %s across %s", path, BACKEND_URLS)
    return None


# ============================================================================
# Command handlers
# ============================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "🤖 *Personal AI Agent*\n\n"
        "I can help you with research, writing, coding, and analysis.\n\n"
        "Just send me a message, or use a command:\n"
        "/ask — ask a question\n"
        "/code — generate code\n"
        "/analyze — analyze text\n"
        "/history — recent tasks\n"
        "/status — budget & usage\n"
        "/tools — list tools\n"
        "/stats — latency stats\n"
        "/skills — skill profile\n"
        "/mcp — MCP readiness\n"
        "/help — full command list",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "📚 *Command Reference*\n\n"
        "*Bot Commands*\n"
        "/ask `<question>` — ask the agent anything\n"
        "/code `<task>` — generate or debug code\n"
        "/analyze `<text>` — summarize or analyze text\n"
        "/status — budget & usage\n"
        "/history — last 5 tasks\n"
        "/tools — list tools\n"
        "/stats — latency stats\n"
        "/skills — skill profile\n"
        "/mcp — MCP readiness\n"
        "/new — start a fresh conversation\n"
        "/help — this message\n\n"
        "*Model Routing*\n"
        "Greetings / short → Free (Llama)\n"
        "Questions / facts → DeepSeek\n"
        "Code tasks → DeepSeek\n"
        "Research / deep dive → Gemini Flash\n"
        "Analysis / planning → Claude Haiku\n"
        '"use sonnet" / premium → Claude Sonnet 4\n'
        "Tool use (web search etc) → Claude Haiku\n\n"
        "*Web UI*\n"
        "http://localhost:3003/commands\n\n"
        "💡 Just send a message directly — no command needed.",
        parse_mode="Markdown",
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ask <your question>")
        return
    await _process_query(update, " ".join(context.args))


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /analyze <text to analyze>")
        return
    await _process_query(update, "Analyze and summarize: " + " ".join(context.args))


async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /code <describe what you need>")
        return
    await _process_query(update, "Write code for: " + " ".join(context.args))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/status/costs")
    if not data:
        await update.message.reply_text("⚠️ Could not reach backend. Is it running?")
        return

    bar_filled = int(data["percent_used"] / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    status_icon = "✅" if data["status"] == "ok" else "⚠️"

    await update.message.reply_text(
        f"💰 *Budget Status*\n\n"
        f"`{bar}` {data['percent_used']:.1f}%\n\n"
        f"Budget:    ${data['budget']:.2f}\n"
        f"This month: ${data['spent_month']:.4f}\n"
        f"Today:      ${data['spent_today']:.4f}\n"
        f"Remaining: ${data['remaining']:.4f}\n\n"
        f"Status: {status_icon} {data['status'].upper()}",
        parse_mode="Markdown",
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/history?limit=5")
    if not data:
        await update.message.reply_text(
            "⚠️ Could not fetch history. Is the database connected?"
        )
        return

    tasks = data.get("tasks", [])
    if not tasks:
        await update.message.reply_text("No tasks yet. Send a message to get started!")
        return

    status_icons = {
        "completed": "✅",
        "running": "🔄",
        "failed": "❌",
        "pending": "⏳",
        "stopped": "⛔",
    }

    lines = [f"📋 *Last {len(tasks)} tasks* (of {data['total']} total)\n"]
    for t in tasks:
        icon = status_icons.get(t["status"], "•")
        query = t["query"][:60] + ("…" if len(t["query"]) > 60 else "")
        cost = f"${t['cost']:.4f}" if t.get("cost") else ""
        lines.append(f"{icon} {query}\n    {cost}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available tools from the backend."""
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/agent/tools")
    if not data:
        await update.message.reply_text(
            "⚠️ Could not fetch tools. Is the backend running?"
        )
        return

    tools = data.get("tools", [])
    total = data.get("total", len(tools))
    if not tools:
        await update.message.reply_text("No tools are currently registered.")
        return

    names = sorted(str(t.get("name") or "") for t in tools if isinstance(t, dict))
    bullet_list = "\n".join(f"• `{n}`" for n in names if n)
    await update.message.reply_text(
        f"🛠 *Available tools* ({total} total)\n\n{bullet_list}",
        parse_mode="Markdown",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show simple latency stats per endpoint, if available."""
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/agent/stats?days=1")
    if not data:
        await update.message.reply_text(
            "⚠️ Could not fetch stats. Is the backend running?"
        )
        return

    rows = data.get("latency_by_endpoint") or []
    if not rows:
        await update.message.reply_text(
            "No latency samples yet. Try running a few tasks first."
        )
        return

    lines = [f"📊 *Latency (last {data.get('window_days', 1)} day)*\n"]
    for r in rows:
        endpoint = r.get("endpoint", "")
        p50 = r.get("p50_ms")
        p95 = r.get("p95_ms")
        p99 = r.get("p99_ms")
        n = r.get("n")
        lines.append(
            f"`{endpoint}` — p50 {p50:.0f}ms, p95 {p95:.0f}ms, p99 {p99:.0f}ms (n={n})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the agent's skill profile (success rate per task type)."""
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/analytics/skills")
    if not data:
        await update.message.reply_text(
            "⚠️ Could not fetch skills. Is the database connected?"
        )
        return

    skills = data.get("skills") or []
    if not skills:
        await update.message.reply_text(
            "No skills computed yet. Run a few tasks first."
        )
        return

    lines = ["🧠 *Skill profile* (top 10)\n"]
    for s in skills[:10]:
        task_type = s.get("task_type", "unknown")
        rate = float(s.get("success_rate") or 0.0) * 100
        uses = int(s.get("total_uses") or 0)
        lines.append(f"`{task_type}` — {rate:.0f}% (uses={uses})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def mcp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show MCP/tool readiness snapshot (from /agent/tools/health)."""
    if not _is_authorized(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    data = await _call_backend("get", "/agent/tools/health")
    if not data:
        await update.message.reply_text(
            "⚠️ Could not fetch tool health. Is the backend running?"
        )
        return

    checks = data.get("checks") or []
    if not checks:
        await update.message.reply_text("No checks returned.")
        return

    total = int(data.get("total") or len(checks))
    ok = int(data.get("healthy_count") or 0)
    lines = [f"🔌 *Tool/MCP health*: {ok}/{total} ok\n"]
    for c in checks[:15]:
        name = c.get("name") or c.get("tool") or "unknown"
        status = "✅" if c.get("ok") else "❌"
        note = c.get("error") or c.get("note") or ""
        tail = f" — {note}" if note else ""
        lines.append(f"{status} `{name}`{tail}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a fresh conversation thread."""
    if not _is_authorized(update):
        return
    chat_id = update.message.chat_id
    _chat_conversations.pop(chat_id, None)
    await update.message.reply_text(
        "🔄 Started a new conversation. Previous context cleared."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages as agent queries."""
    if not _is_authorized(update):
        return
    await _process_query(update, update.message.text)


# ============================================================================
# Core query processor
# ============================================================================


async def _process_query(update: Update, query: str):
    """Send query to backend and reply with the result."""
    await update.message.chat.send_action(ChatAction.TYPING)

    chat_id = update.message.chat_id
    conversation_id = _chat_conversations.get(chat_id)

    data = await _call_backend(
        "post",
        "/agent/run",
        json={
            "query": query,
            "max_iterations": 5,
            "conversation_id": conversation_id,
        },
    )

    if data is None:
        await update.message.reply_text(
            "❌ Agent request failed. Check that the backend is running."
        )
        return

    # Persist conversation_id for this chat thread
    if data.get("conversation_id"):
        _chat_conversations[chat_id] = data["conversation_id"]

    result = data.get("result", "No result returned.")
    cost = data.get("cost", 0)

    reply = _truncate(f"{result}\n\n💰 Cost: ${cost:.4f}")
    await update.message.reply_text(reply)


# ============================================================================
# Entry point
# ============================================================================


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    if not API_KEY:
        raise ValueError("TELEGRAM_BOT_API_KEY/BACKEND_API_KEY is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", new_conversation))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("skills", skills_command))
    app.add_handler(CommandHandler("mcp", mcp_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
