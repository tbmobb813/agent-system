"""Snapshot-style tests for modular system prompt assembly."""

from app.agent.prompts.system_prompt import (
    BASE_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_system_prompt,
)


def test_prompt_version_is_set():
    assert PROMPT_VERSION
    assert "2026" in PROMPT_VERSION


def test_build_minimal_matches_legacy_shape():
    out = build_system_prompt(None, None, "")
    assert out.startswith(BASE_SYSTEM_PROMPT)


def test_build_with_persona_retrieved_fiscal():
    out = build_system_prompt(
        "mem1",
        "extra hint",
        "Be brief.",
        budget_remaining=10.5,
        monthly_budget_usd=30.0,
    )
    assert BASE_SYSTEM_PROMPT in out
    assert "<assistant_profile>" in out
    assert "Be brief." in out
    assert "<retrieved_context>" in out
    assert "mem1" in out
    assert "data only" in out
    assert "Additional context: extra hint" in out
    assert "<fiscal_context>" in out
    assert "$30.00" in out
    assert "$10.50" in out


def test_build_no_fiscal_when_partial_budget_args():
    out = build_system_prompt(
        None, None, "", budget_remaining=5.0, monthly_budget_usd=None
    )
    assert "<fiscal_context>" not in out
    out2 = build_system_prompt(
        None, None, "", budget_remaining=None, monthly_budget_usd=30.0
    )
    assert "<fiscal_context>" not in out2
