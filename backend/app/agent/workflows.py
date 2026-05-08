"""
Declarative multi-step workflows (YAML) executed with the live orchestrator.

Workflow files live under ``backend/data/workflows/*.yaml``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "data" / "workflows"
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _workflow_path(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise ValueError("Invalid workflow name")
    base = _WORKFLOW_DIR.resolve()
    path = (base / f"{name}.yaml").resolve()
    if path.parent != base:
        raise ValueError("Invalid workflow path")
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def load_workflow(name: str) -> dict[str, Any]:
    """Load and parse workflow YAML."""
    path = _workflow_path(name)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Workflow root must be a mapping")
    return data


async def run_named_workflow(
    orchestrator: Any,
    name: str,
    *,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute steps in order. Each step is either:
    - ``tool``: name + ``args`` (optional) → ``ToolRegistry.call``
    - ``agent``: ``query`` (or ``prompt``) → ``orchestrator.run``
    """
    spec = load_workflow(name)
    steps = spec.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Workflow must contain a 'steps' list")

    results: dict[str, Any] = {}
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            continue
        step_name = str(raw.get("name") or f"step_{i}")
        tool = raw.get("tool")
        agent_q = raw.get("query") or raw.get("prompt")
        if tool:
            args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
            try:
                out = await orchestrator.tools.call(str(tool), **args)
            except Exception as e:
                logger.warning(
                    "Workflow %s step %s tool %s failed: %s", name, step_name, tool, e
                )
                results[step_name] = {"error": str(e)}
                continue
            results[step_name] = out
        elif agent_q:
            try:
                text, conv = await orchestrator.run(
                    query=str(agent_q),
                    context=raw.get("context"),
                    tools=raw.get("tools"),
                    user_id=user_id,
                    max_iterations=int(raw.get("max_iterations") or 10),
                    conversation_id=raw.get("conversation_id"),
                    reasoning_effort=raw.get("reasoning_effort"),
                )
            except Exception as e:
                logger.warning(
                    "Workflow %s step %s agent failed: %s", name, step_name, e
                )
                results[step_name] = {"error": str(e)}
                continue
            results[step_name] = {"result": text, "conversation_id": conv}
        else:
            results[step_name] = {"skipped": True, "reason": "no tool or agent query"}

    return {"workflow": spec.get("workflow") or name, "steps": results}
