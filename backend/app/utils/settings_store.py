"""Shared settings persistence helpers."""

import json
import os
import logging

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR = os.path.join(_BACKEND_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", os.path.join(_DATA_DIR, "agent-settings.json"))


def load_settings_dict() -> dict:
    """Load persisted settings from disk, or return empty dict."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings_dict(data: dict) -> None:
    """Persist settings to disk. Errors are logged and swallowed."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        logger.warning("Could not save settings: %s", exc)
