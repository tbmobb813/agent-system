"""
Integration routes for external chat platforms.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.integrations.slack_discord_bot import slack_discord_bot

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/slack/webhook")
async def slack_webhook(
    payload: dict,
    x_bot_secret: str | None = Header(default=None),
):
    """
    Receive Slack events.
    """
    # Slack URL verification challenge flow.
    challenge = payload.get("challenge")
    if challenge:
        return {"challenge": challenge}

    if not slack_discord_bot.verify_webhook_secret(x_bot_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    result = await slack_discord_bot.handle_slack_event(payload)
    return {"status": "ok", "result": result}


@router.post("/discord/webhook")
async def discord_webhook(
    payload: dict,
    x_bot_secret: str | None = Header(default=None),
):
    """
    Receive Discord events/messages.
    """
    if not slack_discord_bot.verify_webhook_secret(x_bot_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    result = await slack_discord_bot.handle_discord_event(payload)
    return {"status": "ok", "result": result}
