"""
Load repo-root agent_pillars.yaml for runtime config (model tiers, MCP servers).

Path: backend/app/utils → parents[3] = repository root.
Override with AGENT_PILLARS_PATH for container/deploy layouts.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_config_cache: dict | None = None
_config_mtime: float | None = None


def pillars_file_path() -> Path:
    env = os.environ.get("AGENT_PILLARS_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    return (here.parents[3] / "agent_pillars.yaml").resolve()


def get_pillar_config(*, force_reload: bool = False) -> dict:
    """
    Return parsed agent_pillars.yaml or {} if missing/unreadable.
    Invalidates cache when the file mtime changes.
    """
    global _config_cache, _config_mtime
    path = pillars_file_path()
    if not path.is_file():
        return {}
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if (
        not force_reload
        and _config_cache is not None
        and _config_mtime == mtime
    ):
        return _config_cache
    try:
        with open(path, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    except Exception:
        _config_cache = {}
    _config_mtime = mtime
    return _config_cache
