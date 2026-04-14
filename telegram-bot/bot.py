"""
Telegram Bot - Access your AI agent from Telegram.
"""

import os
import logging
import httpx
from dotenv import load_dotenv

# Load from local .env first, then fall back to backend .env
_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_dir, ".env"))
load_dotenv(os.path.join(_dir, "..", "backend", ".env"))
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
API_KEY = os.getenv("TELEGRAM_BOT_API_KEY", "sk-agent-telegram-bot")
_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Per-chat conversation tracking: {chat_id: conversation_id}
_chat_conversations: dict[int, str] = {}


def _is_authorized(update: Update) -> bool:
    """Return True only if the message comes from the configured chat ID."""
    if not _ALLOWED_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — rejecting all messages")
        return False
    return update.effective_chat.id == _ALLOWED_CHAT_ID


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
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            fn = getattr(client, method)
            resp = await fn(f"{BACKEND_URL}{path}", headers=HEADERS, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"Backend {method.upper()} {path} → {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Backend request failed: {e}")
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
        "/new — start a fresh conversation\n"
        "/help — this message\n\n"
        "*Model Routing*\n"
        "Greetings / short → Free (Llama)\n"
        "Questions / facts → DeepSeek\n"
        "Code tasks → DeepSeek\n"
        "Research / deep dive → Gemini Flash\n"
        "Analysis / planning → Claude Haiku\n"
        "\"use sonnet\" / premium → Claude Sonnet 4\n"
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
        await update.message.reply_text("⚠️ Could not fetch history. Is the database connected?")
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


async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a fresh conversation thread."""
    if not _is_authorized(update):
        return
    chat_id = update.message.chat_id
    _chat_conversations.pop(chat_id, None)
    await update.message.reply_text("🔄 Started a new conversation. Previous context cleared.")


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

    data = await _call_backend("post", "/agent/run", json={
        "query": query,
        "max_iterations": 5,
        "conversation_id": conversation_id,
    })

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

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", new_conversation))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
