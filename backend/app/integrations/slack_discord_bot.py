"""
Slack and Discord bot integration scaffold.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class SlackDiscordBot:
    """
    Minimal bridge that can be expanded into full bot adapters.
    """

    def __init__(self) -> None:
        self.slack_bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        self.discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "")
        self.webhook_secret = os.getenv("BOT_WEBHOOK_SECRET", "")

    def verify_webhook_secret(self, provided: str | None) -> bool:
        # If no secret is configured, accept for local development.
        if not self.webhook_secret:
            return True
        return bool(provided) and provided == self.webhook_secret

    async def handle_slack_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event", {}) if isinstance(payload, dict) else {}
        text = event.get("text", "") if isinstance(event, dict) else ""
        user = event.get("user", "") if isinstance(event, dict) else ""
        logger.info("Slack event received from user=%s", user or "unknown")
        return {
            "provider": "slack",
            "accepted": True,
            "message_preview": str(text)[:120],
            "user": user or None,
        }

    async def handle_discord_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = payload.get("content", "") if isinstance(payload, dict) else ""
        author = payload.get("author", {}) if isinstance(payload, dict) else {}
        username = author.get("username", "") if isinstance(author, dict) else ""
        logger.info("Discord event received from user=%s", username or "unknown")
        return {
            "provider": "discord",
            "accepted": True,
            "message_preview": str(content)[:120],
            "user": username or None,
        }


slack_discord_bot = SlackDiscordBot()
