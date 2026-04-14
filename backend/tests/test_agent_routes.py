from httpx import ASGITransport, AsyncClient

from app.main import app


class DummyCostTracker:
    def __init__(self, estimate: float, spent: float, last_cost: float = 0.001):
        self._estimate = estimate
        self._spent = spent
        self._last_cost = last_cost

    async def estimate_cost(self, query: str) -> float:
        return self._estimate

    async def get_spent_today(self) -> float:
        return self._spent

    async def get_last_call_cost(self) -> float:
        return self._last_cost


class DummyOrchestrator:
    async def run(self, **kwargs):
        return "mocked result", kwargs.get("conversation_id") or "conv-test"


async def test_run_agent_returns_completed_response():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)

    app.state.agent_orchestrator = DummyOrchestrator()
    app.state.cost_tracker = DummyCostTracker(estimate=0.01, spent=0.0, last_cost=0.0025)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/run',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'Say hello', 'conversation_id': 'conv-123'},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload['status'] == 'completed'
        assert payload['result'] == 'mocked result'
        assert payload['conversation_id'] == 'conv-123'
        assert payload['cost'] == 0.0025
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


async def test_run_agent_returns_402_when_estimate_exceeds_remaining_budget():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)

    app.state.agent_orchestrator = DummyOrchestrator()
    app.state.cost_tracker = DummyCostTracker(estimate=5.0, spent=29.5)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/run',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'Very expensive task'},
            )

        assert response.status_code == 402
        payload = response.json()
        assert payload['error'] == 'Insufficient budget'
        assert payload['budget'] == 30.0
        assert payload['estimated_cost'] == 5.0
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost