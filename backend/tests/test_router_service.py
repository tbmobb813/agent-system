from unittest.mock import AsyncMock

import pytest

from app.agent.router import ModelRouter


def test_sampling_params_for_model_reads_agent_pillars(monkeypatch):
    def fake_pillars():
        # advanced and agent may share the same OpenRouter model id; tier match returns first.
        return {
            "llm": {
                "model_tiers": {
                    "advanced": {"temperature": 0.22, "top_p": 0.91},
                    "agent": {"temperature": 0.22, "top_p": 0.91},
                }
            }
        }

    monkeypatch.setattr("app.agent.router.get_pillar_config", fake_pillars)
    router = ModelRouter()
    model = router.MODELS["agent"]["model"]
    sp = router.sampling_params_for_model(model)
    assert sp["temperature"] == 0.22
    assert sp["top_p"] == 0.91


def test_select_model_forces_free_model_when_budget_is_very_low():
    router = ModelRouter()

    selected = router.select_model("Write code for me", budget_remaining=1.0)

    assert selected == router.MODELS["free"]["model"]


def test_select_model_uses_simple_tier_when_budget_is_moderate():
    router = ModelRouter()

    selected = router.select_model("Explain this quickly", budget_remaining=5.0)

    assert selected == router.MODELS["simple"]["model"]


def test_select_model_respects_prefer_quality_override():
    router = ModelRouter()

    selected = router.select_model(
        "anything", prefer_quality=True, budget_remaining=30.0
    )

    assert selected == router.MODELS["premium"]["model"]


def test_select_model_routes_coding_queries_to_coding_model():
    router = ModelRouter()

    selected = router.select_model(
        "Debug this Python function please", budget_remaining=30.0
    )

    assert selected == router.MODELS["coding"]["model"]


def test_is_complex_for_research_queries():
    router = ModelRouter()

    assert router.is_complex("Provide a comprehensive overview and deep dive") is True


def test_should_plan_true_for_complex_query_with_tools_and_no_history():
    router = ModelRouter()

    assert (
        router.should_plan(
            query="Compare two architectures with pros and cons",
            has_tools=True,
            has_history=False,
        )
        is True
    )


def test_should_plan_false_when_no_tools_available():
    router = ModelRouter()

    assert (
        router.should_plan(
            query="Compare two architectures with pros and cons",
            has_tools=False,
            has_history=False,
        )
        is False
    )


def test_should_plan_false_for_follow_up_with_history():
    router = ModelRouter()

    assert (
        router.should_plan(
            query="Compare two architectures with pros and cons",
            has_tools=True,
            has_history=True,
        )
        is False
    )


@pytest.mark.asyncio
async def test_should_plan_async_matches_keyword_path_by_default():
    router = ModelRouter()

    assert (
        await router.should_plan_async(
            query="Compare two architectures with pros and cons",
            has_tools=True,
            has_history=False,
        )
        is True
    )
    assert (
        await router.should_plan_async(
            query="Compare two architectures with pros and cons",
            has_tools=False,
            has_history=False,
        )
        is False
    )


@pytest.mark.asyncio
async def test_should_plan_async_llm_classifier_respects_llm_label(monkeypatch):
    def pillars_llm():
        return {
            "orchestration": {
                "execution": {"complexity_threshold": "llm_classifier"},
            },
            "llm": {
                "routing_classifier": {"model": "meta-llama/llama-3.1-8b-instruct:free"}
            },
        }

    monkeypatch.setattr("app.agent.router.get_pillar_config", pillars_llm)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "sk-test")

    router = ModelRouter()
    router._classify_query_llm = AsyncMock(return_value="coding")

    # Keyword path would be "coding" → not complex; LLM says coding → no plan
    assert (
        await router.should_plan_async(
            query="Debug this Python traceback",
            has_tools=True,
            has_history=False,
        )
        is False
    )

    router._classify_query_llm = AsyncMock(return_value="complex")
    assert (
        await router.should_plan_async(
            query="Debug this Python traceback",
            has_tools=True,
            has_history=False,
        )
        is True
    )


@pytest.mark.asyncio
async def test_should_plan_async_without_api_key_uses_keyword_even_if_yaml_llm_mode(
    monkeypatch,
):
    def pillars_llm():
        return {
            "orchestration": {
                "execution": {"complexity_threshold": "llm_classifier"},
            },
        }

    monkeypatch.setattr("app.agent.router.get_pillar_config", pillars_llm)
    monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "")

    router = ModelRouter()

    assert (
        await router.should_plan_async(
            query="Compare two architectures with pros and cons",
            has_tools=True,
            has_history=False,
        )
        is True
    )


def test_complexity_mode_reads_pillars(monkeypatch):
    def pillars():
        return {
            "orchestration": {
                "execution": {"complexity_threshold": "llm_classifier"},
            },
        }

    monkeypatch.setattr("app.agent.router.get_pillar_config", pillars)
    assert ModelRouter().complexity_mode() == "llm_classifier"


def test_should_remember_false_for_followup_transactional_edit():
    router = ModelRouter()

    assert (
        router.should_remember(
            query="Can you make that shorter?",
            has_history=True,
            response="Updated.",
        )
        is False
    )


def test_should_remember_true_for_substantive_followup_question():
    router = ModelRouter()

    assert (
        router.should_remember(
            query="What are the security implications of this architecture change?",
            has_history=True,
            response="The main implications are in auth boundaries and data exposure.",
        )
        is True
    )


def test_get_next_fallback_returns_next_model_in_chain():
    router = ModelRouter()

    first = router.FALLBACK_CHAIN[0]
    second = router.FALLBACK_CHAIN[1]

    assert router.get_next_fallback(first) == second


def test_get_next_fallback_for_unknown_model_returns_chain_head():
    router = ModelRouter()

    assert router.get_next_fallback("unknown/model") == router.FALLBACK_CHAIN[0]
