"""Versioned system prompt assembly for the agent."""

from app.agent.prompts.system_prompt import (
    BASE_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_system_prompt,
)

__all__ = ["BASE_SYSTEM_PROMPT", "PROMPT_VERSION", "build_system_prompt"]
