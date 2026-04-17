"""
Settings routes — modular APIRouter for /settings endpoints.

Single-user personal system: settings are stored in a JSON file,
with no per-user DB lookup required. This avoids UUID/RLS issues
and works even when the DB is not fully set up.
"""

import logging
from fastapi import APIRouter, Depends

from app.models import Settings as UserSettings
from app.utils.auth import verify_api_key
from app.utils.persona_loader import build_persona_prompt
from app.utils.settings_store import load_settings_dict, save_settings_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


def _load() -> dict:
    return load_settings_dict()


def _save(data: dict) -> None:
    save_settings_dict(data)


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


@router.get("/persona/preview")
async def get_persona_preview(api_key: str = Depends(verify_api_key)):
    """Return the resolved persona prompt block for debugging settings and file paths."""
    data = _load()
    normalized = UserSettings(**data).model_dump() if data else UserSettings().model_dump()
    preview = build_persona_prompt(normalized)
    return {
        "enabled": normalized["agent_persona_enabled"],
        "path": normalized["agent_persona_path"],
        "preview": preview,
    }
