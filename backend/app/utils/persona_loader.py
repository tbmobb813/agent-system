"""Load persona/policy markdown files for system prompt injection."""

from __future__ import annotations

import os
from typing import Optional

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_DIR = os.path.dirname(_BACKEND_DIR)
_DEFAULT_DIR = os.path.join(_BACKEND_DIR, "data", "persona")

_FILE_ORDER = [
    ("operations", "operations.md"),
    ("soul", "soul.md"),
    ("style", "style.md"),
    ("skill", "skill.md"),
]

_MAX_FILE_CHARS = 8000


def _resolve_persona_dir(configured_path: Optional[str]) -> str:
    path = (configured_path or "").strip()
    if not path:
        return _DEFAULT_DIR

    if os.path.isabs(path):
        return path

    candidates = [
        os.path.join(_BACKEND_DIR, path),
        os.path.join(_PROJECT_DIR, path),
    ]
    if path.startswith("backend/"):
        candidates.append(os.path.join(_PROJECT_DIR, path[len("backend/") :]))

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    # If missing, fall back to first candidate for clear logging/debugging behavior.
    return candidates[0]


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().replace("\x00", "")
            return text.strip()[:_MAX_FILE_CHARS]
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def build_persona_prompt(settings_data: Optional[dict] = None) -> str:
    """Build a structured persona block from markdown files."""
    settings_data = settings_data or {}
    if not settings_data.get("agent_persona_enabled", True):
        return ""

    persona_dir = _resolve_persona_dir(settings_data.get("agent_persona_path"))

    sections: list[str] = []
    for label, filename in _FILE_ORDER:
        content = _read_file(os.path.join(persona_dir, filename))
        if not content:
            continue
        sections.append(f"<{label}>\n{content}\n</{label}>")

    return "\n\n".join(sections)
