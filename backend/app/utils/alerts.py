"""
Budget alert system.

Sends notifications when spending hits 80% and 95% of the monthly budget.
Supports Telegram (primary) and any webhook URL (Slack, Discord, etc.).

Deduplication: each threshold fires at most once per calendar month.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Tracks which budget thresholds have already been alerted this month
    and sends notifications via Telegram and/or webhook.
    """

    THRESHOLDS = [
        (0.80, "⚠️ Budget Warning"),
        (0.95, "🚨 Budget Critical"),
    ]

    def __init__(self):
        # Track which thresholds have fired: {(year, month, threshold): True}
        self._sent: dict[tuple, bool] = {}

    async def check_and_notify(self, spent: float, budget: float) -> None:
        """
        Called after every tracked API cost. Fires alerts at each threshold
        at most once per month.
        """
        if budget <= 0:
            return

        percent = spent / budget
        now = datetime.utcnow()
        period = (now.year, now.month)

        for threshold, label in self.THRESHOLDS:
            key = (*period, threshold)
            if percent >= threshold and not self._sent.get(key):
                self._sent[key] = True
                await self._send(label, spent, budget, percent * 100)

    async def _send(
        self,
        label: str,
        spent: float,
        budget: float,
        percent: float,
    ) -> None:
        remaining = budget - spent
        bar_filled = int(percent / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)

        message = (
            f"{label}\n\n"
            f"`{bar}` {percent:.1f}%\n\n"
            f"Spent:     ${spent:.4f}\n"
            f"Budget:    ${budget:.2f}\n"
            f"Remaining: ${remaining:.4f}\n\n"
            f"_Monthly budget resets on the 1st._"
        )

        await self._telegram(message)
        await self._webhook(label, spent, budget, percent)

    async def _telegram(self, message: str) -> None:
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            logger.debug("Telegram alert skipped — BOT_TOKEN or CHAT_ID not set")
            return

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                })
                if resp.status_code == 200:
                    logger.info(f"Budget alert sent via Telegram")
                else:
                    logger.warning(f"Telegram alert failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Telegram alert error: {e}")

    async def _webhook(
        self,
        label: str,
        spent: float,
        budget: float,
        percent: float,
    ) -> None:
        if not settings.ALERT_WEBHOOK_URL:
            return

        payload = {
            "text": f"{label}: {percent:.1f}% of ${budget:.2f} budget used (${spent:.4f} spent)",
            "spent": spent,
            "budget": budget,
            "percent": percent,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(settings.ALERT_WEBHOOK_URL, json=payload)
                if resp.status_code < 300:
                    logger.info("Budget alert sent via webhook")
                else:
                    logger.warning(f"Webhook alert failed: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Webhook alert error: {e}")


# Module-level singleton
alert_manager = AlertManager()
