"""
Settings routes — modular APIRouter for /settings endpoints.

Single-user personal system: settings are stored in a JSON file,
with no per-user DB lookup required. This avoids UUID/RLS issues
and works even when the DB is not fully set up.
"""

import json
import os
import logging
from fastapi import APIRouter, Depends

from app.models import Settings as UserSettings
from app.utils.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "/tmp/agent-settings.json")


def _load() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save settings: {e}")


@router.get("")
async def get_settings(api_key: str = Depends(verify_api_key)):
    """Return current settings (defaults if not yet saved)."""
    data = _load()
    return UserSettings(**data) if data else UserSettings()


@router.post("")
async def update_settings(
    body: UserSettings,
    api_key: str = Depends(verify_api_key),
):
    """Persist settings to disk."""
    _save(body.model_dump())
    return {"status": "updated", "settings": body}
