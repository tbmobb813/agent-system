from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_slack_webhook_returns_challenge_without_secret():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/integrations/slack/webhook",
            json={"challenge": "abc123"},
        )

    assert response.status_code == 200
    assert response.json()["challenge"] == "abc123"


async def test_slack_webhook_accepts_event():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/integrations/slack/webhook",
            json={"event": {"text": "hello from slack", "user": "U123"}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["provider"] == "slack"


async def test_discord_webhook_accepts_event():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/integrations/discord/webhook",
            json={"content": "hello from discord", "author": {"username": "tester"}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["provider"] == "discord"
