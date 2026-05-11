"""
Connectors — manage third-party integrations.

Tokens are stored in the settings JSON file (same store used by /settings).
GET responses never return raw tokens — only masked status.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.auth import verify_api_key
from app.utils.settings_store import load_settings_dict, save_settings_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["connectors"])

# ── Connector registry ────────────────────────────────────────────────────────
# Extend this list to add new connectors.

CONNECTOR_DEFS: list[dict[str, Any]] = [
    {
        "id": "github",
        "name": "GitHub",
        "description": "Read repos, issues, PRs, and files. Create issues and comments.",
        "token_label": "Personal Access Token",
        "token_help": "https://github.com/settings/tokens — needs repo + issues scopes",
        "actions": [
            "search_repos",
            "get_repo",
            "list_issues",
            "get_issue",
            "create_issue",
            "comment_issue",
            "list_prs",
            "get_pr",
            "get_file",
            "list_commits",
            "get_user",
        ],
    },
]

CONNECTOR_IDS = {c["id"] for c in CONNECTOR_DEFS}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_connectors() -> dict[str, dict]:
    return load_settings_dict().get("connectors", {})


def _save_connectors(connectors: dict[str, dict]) -> None:
    data = load_settings_dict()
    data["connectors"] = connectors
    save_settings_dict(data)


def _mask(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "•" * len(token)
    return token[:4] + "•" * (len(token) - 8) + token[-4:]


def _connector_status(cid: str, stored: dict) -> dict[str, Any]:
    cfg = stored.get(cid, {})
    has_token = bool(cfg.get("token"))
    defn = next(d for d in CONNECTOR_DEFS if d["id"] == cid)
    return {
        "id": cid,
        "name": defn["name"],
        "description": defn["description"],
        "token_label": defn["token_label"],
        "token_help": defn["token_help"],
        "actions": defn["actions"],
        "configured": has_token,
        "enabled": cfg.get("enabled", False) if has_token else False,
        "token_preview": _mask(cfg.get("token", "")) if has_token else "",
    }


# ── Models ────────────────────────────────────────────────────────────────────


class ConnectorUpdate(BaseModel):
    token: Optional[str] = Field(
        default=None, description="Leave null to keep existing token"
    )
    enabled: bool = Field(default=True)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_connectors(api_key: str = Depends(verify_api_key)):
    """Return all connectors with masked status — never raw tokens."""
    stored = _load_connectors()
    return [_connector_status(c["id"], stored) for c in CONNECTOR_DEFS]


@router.get("/{connector_id}")
async def get_connector(connector_id: str, api_key: str = Depends(verify_api_key)):
    if connector_id not in CONNECTOR_IDS:
        raise HTTPException(
            status_code=404, detail=f"Connector not found: {connector_id}"
        )
    stored = _load_connectors()
    return _connector_status(connector_id, stored)


@router.post("/{connector_id}")
async def save_connector(
    connector_id: str,
    body: ConnectorUpdate,
    api_key: str = Depends(verify_api_key),
):
    """Save token and/or toggle enabled state."""
    if connector_id not in CONNECTOR_IDS:
        raise HTTPException(
            status_code=404, detail=f"Connector not found: {connector_id}"
        )

    stored = _load_connectors()
    cfg = stored.get(connector_id, {})

    if body.token is not None:
        cfg["token"] = body.token.strip()

    has_token = bool(cfg.get("token"))
    cfg["enabled"] = body.enabled if has_token else False

    stored[connector_id] = cfg
    _save_connectors(stored)

    return _connector_status(connector_id, stored)


@router.delete("/{connector_id}/token")
async def clear_connector_token(
    connector_id: str, api_key: str = Depends(verify_api_key)
):
    """Remove the stored token and disable the connector."""
    if connector_id not in CONNECTOR_IDS:
        raise HTTPException(
            status_code=404, detail=f"Connector not found: {connector_id}"
        )

    stored = _load_connectors()
    stored[connector_id] = {"token": "", "enabled": False}
    _save_connectors(stored)
    return _connector_status(connector_id, stored)


@router.get("/{connector_id}/test")
async def test_connector(connector_id: str, api_key: str = Depends(verify_api_key)):
    """Ping the connector's API to verify the token works."""
    if connector_id not in CONNECTOR_IDS:
        raise HTTPException(
            status_code=404, detail=f"Connector not found: {connector_id}"
        )

    stored = _load_connectors()
    cfg = stored.get(connector_id, {})
    token = cfg.get("token", "")

    if not token:
        from app.config import settings

        if connector_id == "github":
            token = settings.GITHUB_TOKEN

    if not token:
        return {"ok": False, "detail": "No token configured"}

    if connector_id == "github":
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            if r.status_code == 200:
                d = r.json()
                return {
                    "ok": True,
                    "detail": f"Authenticated as @{d.get('login', '?')}",
                }
            elif r.status_code == 401:
                return {
                    "ok": False,
                    "detail": "Token rejected — check scopes or expiry",
                }
            else:
                return {"ok": False, "detail": f"GitHub returned {r.status_code}"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    return {"ok": False, "detail": f"Test not implemented for {connector_id}"}
