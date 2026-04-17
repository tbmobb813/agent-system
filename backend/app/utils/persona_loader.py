"""Load persona/policy markdown files for system prompt injection."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_DIR = os.path.dirname(_BACKEND_DIR)
_DEFAULT_DIR = os.path.join(_BACKEND_DIR, "data", "persona")

_FILE_ORDER = [
    ("operations", "operations.md"),
    ("soul", "soul.md"),
    ("style", "style.md"),
    ("skill", "skill.md"),
    ("memory", "memory.md"),
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
    if not os.path.isdir(persona_dir):
        logger.warning("Persona directory does not exist: %s", persona_dir)
        return ""

    sections: list[str] = []
    missing_files: list[str] = []
    for label, filename in _FILE_ORDER:
        file_path = os.path.join(persona_dir, filename)
        content = _read_file(file_path)
        if not content:
            missing_files.append(filename)
            continue
        sections.append(f"<{label}>\n{content}\n</{label}>")

    if missing_files:
        logger.warning(
            "Persona files missing or empty in %s: %s",
            persona_dir,
            ", ".join(missing_files),
        )

    return "\n\n".join(sections)
