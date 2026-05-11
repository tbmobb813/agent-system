from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_slack_webhook_returns_challenge_without_secret():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/integrations/slack/webhook",
            json={"challenge": "abc123"},
        )

    assert response.status_code == 200
    assert response.json()["challenge"] == "abc123"


async def test_slack_webhook_rejects_event_without_secret_by_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/integrations/slack/webhook",
            json={"event": {"text": "hello from slack", "user": "U123"}},
        )

    assert response.status_code == 401


async def test_slack_webhook_accepts_event_with_explicit_insecure_flag(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.slack_discord_bot.slack_discord_bot.allow_insecure_webhooks",
        True,
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/integrations/slack/webhook",
                json={"event": {"text": "hello from slack", "user": "U123"}},
            )
    finally:
        monkeypatch.setattr(
            "app.integrations.slack_discord_bot.slack_discord_bot.allow_insecure_webhooks",
            False,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["provider"] == "slack"


async def test_discord_webhook_accepts_event_with_secret_header(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.slack_discord_bot.slack_discord_bot.webhook_secret",
        "test-secret",
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/integrations/discord/webhook",
                headers={"X-Bot-Secret": "test-secret"},
                json={
                    "content": "hello from discord",
                    "author": {"username": "tester"},
                },
            )
    finally:
        monkeypatch.setattr(
            "app.integrations.slack_discord_bot.slack_discord_bot.webhook_secret", ""
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["provider"] == "discord"


async def test_discord_webhook_rejects_event_without_secret_header(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.slack_discord_bot.slack_discord_bot.webhook_secret",
        "test-secret",
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/integrations/discord/webhook",
                json={
                    "content": "hello from discord",
                    "author": {"username": "tester"},
                },
            )
    finally:
        monkeypatch.setattr(
            "app.integrations.slack_discord_bot.slack_discord_bot.webhook_secret", ""
        )

    assert response.status_code == 401
