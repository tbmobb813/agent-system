from app.agent.router import ModelRouter


def test_select_model_forces_free_model_when_budget_is_very_low():
    router = ModelRouter()

    selected = router.select_model('Write code for me', budget_remaining=1.0)

    assert selected == router.MODELS['free']['model']


def test_select_model_uses_simple_tier_when_budget_is_moderate():
    router = ModelRouter()

    selected = router.select_model('Explain this quickly', budget_remaining=5.0)

    assert selected == router.MODELS['simple']['model']


def test_select_model_respects_prefer_quality_override():
    router = ModelRouter()

    selected = router.select_model('anything', prefer_quality=True, budget_remaining=30.0)

    assert selected == router.MODELS['premium']['model']


def test_select_model_routes_coding_queries_to_coding_model():
    router = ModelRouter()

    selected = router.select_model('Debug this Python function please', budget_remaining=30.0)

    assert selected == router.MODELS['coding']['model']


def test_is_complex_for_research_queries():
    router = ModelRouter()

    assert router.is_complex('Provide a comprehensive overview and deep dive') is True


def test_get_next_fallback_returns_next_model_in_chain():
    router = ModelRouter()

    first = router.FALLBACK_CHAIN[0]
    second = router.FALLBACK_CHAIN[1]

    assert router.get_next_fallback(first) == second


def test_get_next_fallback_for_unknown_model_returns_chain_head():
    router = ModelRouter()

    assert router.get_next_fallback('unknown/model') == router.FALLBACK_CHAIN[0]