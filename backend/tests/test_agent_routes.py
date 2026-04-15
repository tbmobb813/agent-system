from httpx import ASGITransport, AsyncClient
import uuid
from app.models import ExecutionEvent, EventType

from app.main import app


class DummyCostTracker:
    def __init__(self, estimate: float, spent: float, last_cost: float = 0.001):
        self._estimate = estimate
        self._spent = spent
        self._last_cost = last_cost
        self.popped_task_ids = []

    async def estimate_cost(self, query: str) -> float:
        return self._estimate

    async def get_spent_today(self) -> float:
        return self._spent

    async def get_spent_month(self) -> float:
        return self._spent

    async def get_last_call_cost(self, task_id=None) -> float:
        return self._last_cost

    def get_last_model(self, task_id=None) -> str | None:
        return 'test-model'

    def get_last_usage(self, task_id=None) -> dict:
        return {'input': 10, 'output': 5}

    def _pop_call_info(self, task_id: str) -> dict:
        self.popped_task_ids.append(task_id)
        return {
            'cost': self._last_cost,
            'model': 'test-model',
            'usage': {'input': 10, 'output': 5},
        }


class DummyOrchestrator:
    async def run(self, **kwargs):
        return "mocked result", kwargs.get("conversation_id") or "conv-test"


class DummyStreamOrchestrator:
    def __init__(self, stop_ok: bool = True):
        self.stop_ok = stop_ok

    async def stream(self, **kwargs):
        yield ExecutionEvent(type=EventType.STATUS, content='thinking...')
        yield ExecutionEvent(type=EventType.TEXT_DELTA, content='partial answer')
        yield ExecutionEvent(type=EventType.DONE, content='done', conversation_id='conv-stream')

    async def stop_task(self, task_id: str) -> bool:
        return self.stop_ok


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
        assert payload['model_used'] == 'test-model'
        assert payload['tokens'] == {'input': 10, 'output': 5}
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


async def test_stream_agent_emits_budget_error_when_over_budget():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)

    app.state.agent_orchestrator = DummyStreamOrchestrator()
    app.state.cost_tracker = DummyCostTracker(estimate=50.0, spent=0.0)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/stream',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'too expensive'},
            )

        assert response.status_code == 200
        text = response.text
        assert '"type": "error"' in text
        assert 'Insufficient budget' in text
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


async def test_stream_agent_cleans_cost_tracker_call_info_on_completion():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)

    tracker = DummyCostTracker(estimate=0.01, spent=0.0, last_cost=0.003)
    app.state.agent_orchestrator = DummyStreamOrchestrator()
    app.state.cost_tracker = tracker

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/stream',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'stream and finish'},
            )

        assert response.status_code == 200
        assert '"type": "done"' in response.text
        assert len(tracker.popped_task_ids) == 1
        uuid.UUID(tracker.popped_task_ids[0])
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


class TimeoutStreamOrchestrator:
    async def stream(self, **kwargs):
        if False:
            yield None


async def test_stream_agent_times_out_cleanly(monkeypatch):
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)
    original_timeout = app.state if False else None

    app.state.agent_orchestrator = TimeoutStreamOrchestrator()
    app.state.cost_tracker = DummyCostTracker(estimate=0.01, spent=0.0)

    monkeypatch.setattr('app.routes.agent.settings.MAX_STREAM_SECONDS', 0)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/stream',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'will timeout'},
            )

        assert response.status_code == 200
        assert 'Run timed out after 0s' in response.text
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


async def test_stop_agent_returns_stopped_for_known_task():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    app.state.agent_orchestrator = DummyStreamOrchestrator(stop_ok=True)

    task_id = '11111111-1111-1111-1111-111111111111'
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                f'/agent/stop?task_id={task_id}',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload['status'] == 'stopped'
        assert payload['task_id'] == task_id
    finally:
        app.state.agent_orchestrator = original_orch


async def test_stop_agent_returns_404_for_unknown_task():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    app.state.agent_orchestrator = DummyStreamOrchestrator(stop_ok=False)

    task_id = '22222222-2222-2222-2222-222222222222'
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                f'/agent/stop?task_id={task_id}',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
            )

        assert response.status_code == 404
        assert 'not found' in response.json()['detail']
    finally:
        app.state.agent_orchestrator = original_orch


async def test_stop_agent_rejects_invalid_task_id_format():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    app.state.agent_orchestrator = DummyStreamOrchestrator(stop_ok=True)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/stop?task_id=not-a-uuid',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
            )

        assert response.status_code == 422
    finally:
        app.state.agent_orchestrator = original_orch


async def test_stop_agent_rejects_non_uuid_36_char_value():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    app.state.agent_orchestrator = DummyStreamOrchestrator(stop_ok=True)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/stop?task_id=123456789012345678901234567890123456',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
            )

        assert response.status_code == 422
    finally:
        app.state.agent_orchestrator = original_orch


async def test_run_agent_returns_503_when_orchestrator_missing():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)
    app.state.agent_orchestrator = None
    app.state.cost_tracker = DummyCostTracker(estimate=0.01, spent=0.0)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/run',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'Say hello'},
            )

        assert response.status_code == 503
        assert response.json()['detail'] == 'Agent not ready'
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


async def test_run_agent_returns_503_when_cost_tracker_missing():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    original_cost = getattr(app.state, "cost_tracker", None)
    app.state.agent_orchestrator = DummyOrchestrator()
    app.state.cost_tracker = None

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.post(
                '/agent/run',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
                json={'query': 'Say hello'},
            )

        assert response.status_code == 503
        assert response.json()['detail'] == 'Cost tracker not initialized'
    finally:
        app.state.agent_orchestrator = original_orch
        app.state.cost_tracker = original_cost


class DummyToolOrchestrator:
    def get_available_tools(self):
        return ['web_search', 'api_call']


async def test_list_tools_returns_available_tools():
    original_orch = getattr(app.state, "agent_orchestrator", None)
    app.state.agent_orchestrator = DummyToolOrchestrator()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.get(
                '/agent/tools',
                headers={'Authorization': 'Bearer sk-agent-local-dev'},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload['total'] == 2
        assert payload['tools'] == ['web_search', 'api_call']
    finally:
        app.state.agent_orchestrator = original_orch


async def test_list_models_returns_routing_info():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get(
            '/agent/models',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['routing_strategy'] == 'complexity_based'
    assert isinstance(payload['models'], dict)
