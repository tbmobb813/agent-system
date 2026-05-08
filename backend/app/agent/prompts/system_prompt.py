"""Assemble the main system prompt for agent runs."""

from __future__ import annotations

from typing import Optional

from . import guardrails

# Bump when changing base prompt or guardrail fragments (correlate with decisions.reasoning).
PROMPT_VERSION = "2026-05-07-1"

BASE_SYSTEM_PROMPT = """You are a capable personal AI assistant with access to tools.

Guidelines:
- Use tools when you need current information, need to interact with external systems, or when computation would help.
- You can call multiple tools across multiple rounds — each tool result is fed back to you.
- When you have enough information, respond directly without calling any more tools.
- Be concise and direct. Don't explain what you're about to do — just do it.
- If a tool fails, try a different approach or answer from your own knowledge."""


def build_system_prompt(
    retrieved_context: Optional[str],
    extra_context: Optional[str],
    persona_prompt: str,
    *,
    budget_remaining: Optional[float] = None,
    monthly_budget_usd: Optional[float] = None,
) -> str:
    """Build the static + injected system prompt (same structure as legacy orchestrator)."""
    system = BASE_SYSTEM_PROMPT
    refusal = guardrails.refusal_criteria()
    if refusal:
        system += refusal

    system += guardrails.assistant_profile_section(persona_prompt or "")

    if retrieved_context:
        system += guardrails.retrieved_context_section(retrieved_context)

    if extra_context:
        system += f"\n\nAdditional context: {extra_context}"

    if budget_remaining is not None and monthly_budget_usd is not None:
        system += guardrails.fiscal_context_section(
            budget_remaining, monthly_budget_usd
        )

    return system
