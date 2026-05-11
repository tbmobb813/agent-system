"""Tests for app/routes/connectors.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.routes.connectors as conn_routes
from app.main import app
from app.routes.connectors import _mask

AUTH = {"Authorization": "Bearer sk-agent-local-dev"}


# ── _mask helper ──────────────────────────────────────────────────────────────


def test_mask_empty_token():
    assert _mask("") == ""


def test_mask_short_token():
    assert _mask("abc") == "•••"


def test_mask_long_token():
    masked = _mask("ghp_abcdefghijklmnop")
    assert masked.startswith("ghp_")
    assert masked.endswith("mnop")
    assert "•" in masked


# ── GET /connectors ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_connectors_returns_all_unconfigured(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    github = next(c for c in data if c["id"] == "github")
    assert github["configured"] is False
    assert github["enabled"] is False
    assert github["token_preview"] == ""


@pytest.mark.asyncio
async def test_list_connectors_shows_configured_github(monkeypatch):
    monkeypatch.setattr(
        conn_routes,
        "_load_connectors",
        lambda: {"github": {"token": "ghp_supersecrettoken", "enabled": True}},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors", headers=AUTH)

    assert r.status_code == 200
    github = next(c for c in r.json() if c["id"] == "github")
    assert github["configured"] is True
    assert github["enabled"] is True
    assert "ghp_supersecrettoken" not in github["token_preview"]
    assert "•" in github["token_preview"]


# ── GET /connectors/{id} ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_connector_not_found(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors/nonexistent", headers=AUTH)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_connector_github_unconfigured(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors/github", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["id"] == "github"
    assert r.json()["configured"] is False


# ── POST /connectors/{id} ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_connector_not_found(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})
    monkeypatch.setattr(conn_routes, "_save_connectors", lambda _: None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.post("/connectors/bogus", headers=AUTH, json={"enabled": True})

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_save_connector_sets_token_and_enables(monkeypatch):
    saved = {}
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})
    monkeypatch.setattr(conn_routes, "_save_connectors", lambda d: saved.update(d))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.post(
            "/connectors/github",
            headers=AUTH,
            json={"token": "ghp_newtoken", "enabled": True},
        )

    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert data["enabled"] is True
    assert saved["github"]["token"] == "ghp_newtoken"


@pytest.mark.asyncio
async def test_save_connector_without_token_keeps_existing(monkeypatch):
    existing = {"github": {"token": "ghp_existing", "enabled": False}}
    saved = {}
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: dict(existing))
    monkeypatch.setattr(conn_routes, "_save_connectors", lambda d: saved.update(d))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.post(
            "/connectors/github",
            headers=AUTH,
            json={"enabled": True},
        )

    assert r.status_code == 200
    assert saved["github"]["token"] == "ghp_existing"
    assert saved["github"]["enabled"] is True


@pytest.mark.asyncio
async def test_save_connector_no_token_forces_disabled(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})
    saved = {}
    monkeypatch.setattr(conn_routes, "_save_connectors", lambda d: saved.update(d))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.post(
            "/connectors/github",
            headers=AUTH,
            json={"enabled": True},
        )

    assert r.status_code == 200
    assert r.json()["enabled"] is False


# ── DELETE /connectors/{id}/token ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_token_not_found(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.delete("/connectors/bogus/token", headers=AUTH)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_clear_token_removes_and_disables(monkeypatch):
    existing = {"github": {"token": "ghp_token", "enabled": True}}
    saved = {}
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: dict(existing))
    monkeypatch.setattr(conn_routes, "_save_connectors", lambda d: saved.update(d))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.delete("/connectors/github/token", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["configured"] is False
    assert saved["github"]["token"] == ""
    assert saved["github"]["enabled"] is False


# ── GET /connectors/{id}/test ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_test_connector_not_found(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors/bogus/test", headers=AUTH)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_test_connector_no_token_returns_not_ok(monkeypatch):
    monkeypatch.setattr(conn_routes, "_load_connectors", lambda: {})
    monkeypatch.setattr(conn_routes, "settings", MagicMock(GITHUB_TOKEN=""))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        r = await client.get("/connectors/github/test", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "No token" in r.json()["detail"]


@pytest.mark.asyncio
async def test_test_connector_github_success(monkeypatch):
    monkeypatch.setattr(
        conn_routes,
        "_load_connectors",
        lambda: {"github": {"token": "ghp_valid", "enabled": True}},
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"login": "octocat"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.routes.connectors.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            r = await client.get("/connectors/github/test", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "octocat" in r.json()["detail"]


@pytest.mark.asyncio
async def test_test_connector_github_invalid_token(monkeypatch):
    monkeypatch.setattr(
        conn_routes,
        "_load_connectors",
        lambda: {"github": {"token": "bad_token", "enabled": True}},
    )

    mock_response = MagicMock()
    mock_response.status_code = 401

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.routes.connectors.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            r = await client.get("/connectors/github/test", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "rejected" in r.json()["detail"]


@pytest.mark.asyncio
async def test_test_connector_github_unexpected_status(monkeypatch):
    monkeypatch.setattr(
        conn_routes,
        "_load_connectors",
        lambda: {"github": {"token": "ghp_token", "enabled": True}},
    )

    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.routes.connectors.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            r = await client.get("/connectors/github/test", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "500" in r.json()["detail"]


@pytest.mark.asyncio
async def test_test_connector_github_network_error(monkeypatch):
    monkeypatch.setattr(
        conn_routes,
        "_load_connectors",
        lambda: {"github": {"token": "ghp_token", "enabled": True}},
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("app.routes.connectors.httpx.AsyncClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            r = await client.get("/connectors/github/test", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is False
