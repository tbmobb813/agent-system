from types import SimpleNamespace

from app.agent.orchestrator import AgentOrchestrator
from app.models import EventType


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = responses

    async def create(self, **kwargs):
        if not self._responses:
            raise RuntimeError('No fake responses configured')
        return self._responses.pop(0)


class _FakeChat:
    def __init__(self, responses):
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _FakeChat(responses)


class _FakeCompletionsWithErrors:
    def __init__(self, responses_or_errors):
        self._items = responses_or_errors

    async def create(self, **kwargs):
        if not self._items:
            raise RuntimeError('No fake responses configured')
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeChatWithErrors:
    def __init__(self, responses_or_errors):
        self.completions = _FakeCompletionsWithErrors(responses_or_errors)


class _FakeClientWithErrors:
    def __init__(self, responses_or_errors):
        self.chat = _FakeChatWithErrors(responses_or_errors)


def _response_with_text(text: str, prompt_tokens: int = 10, completion_tokens: int = 5):
    message = SimpleNamespace(content=text, tool_calls=[])
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _response_with_tool_call(name: str, arguments_json: str, call_id: str = 'call-1'):
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments_json),
    )
    message = SimpleNamespace(content='calling tool', tool_calls=[tool_call])
    usage = SimpleNamespace(prompt_tokens=8, completion_tokens=2)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


async def test_stream_without_tool_calls_emits_text_and_done(monkeypatch):
    saved = {'turn': False, 'memory': False}
    fake_response = _response_with_text('Hello orchestrator test')

    async def _get_or_create(conversation_id, user_id=None):
        return conversation_id or 'conv-1'

    async def _load_messages(conversation_id):
        return []

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        saved['turn'] = True

    async def _save_interaction(**kwargs):
        saved['memory'] = True

    async def _memory_context(query, user_id=None):
        return ''

    async def _build_context(query, user_id=None):
        return ''

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClient([fake_response]))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.get_context_for_query', _memory_context)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [])

    events = [
        event async for event in orch.stream(query='Say hello', user_id='u1', max_iterations=2)
    ]
    event_types = [event.type for event in events]
    full_text = ''.join((event.content or '') for event in events if event.type == EventType.TEXT_DELTA)

    assert EventType.STATUS in event_types
    assert EventType.TEXT_DELTA in event_types
    assert event_types[-1] == EventType.DONE
    assert 'Hello orchestrator test' in full_text
    assert saved['turn'] is True
    assert saved['memory'] is True


async def test_stream_with_tool_call_emits_tool_events_then_final_text(monkeypatch):
    responses = [
        _response_with_tool_call('web_search', '{"query":"weather"}'),
        _response_with_text('Tool result summarized'),
    ]

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-tools'

    async def _load_messages(conversation_id):
        return []

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        return None

    async def _save_interaction(**kwargs):
        return None

    async def _memory_context(query, user_id=None):
        return ''

    async def _build_context(query, user_id=None):
        return ''

    async def _tool_call(name, **kwargs):
        return 'sunny and warm'

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClient(responses))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.get_context_for_query', _memory_context)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [{'type': 'function'}])
    monkeypatch.setattr(orch.tools, 'call', _tool_call)

    events = [
        event async for event in orch.stream(query='Use tool please', user_id='u1', max_iterations=3)
    ]
    event_types = [event.type for event in events]

    assert EventType.TOOL_CALL in event_types
    assert EventType.TOOL_RESULT in event_types
    assert EventType.TEXT_DELTA in event_types
    assert event_types[-1] == EventType.DONE


async def test_stop_task_and_list_tools(monkeypatch):
    orch = AgentOrchestrator(cost_tracker=None)
    orch.active_tasks['t1'] = SimpleNamespace(status=None)

    assert await orch.stop_task('missing') is False
    assert await orch.stop_task('t1') is True

    monkeypatch.setattr(orch.tools, 'list_tools', lambda: ['web_search'])
    assert orch.get_available_tools() == ['web_search']


async def test_stream_emits_stopped_status_when_cancelled_before_iteration(monkeypatch):
    async def _get_or_create(conversation_id, user_id=None):
        return conversation_id or 'conv-stop'

    async def _load_messages(conversation_id):
        return []

    async def _estimate_tokens(conversation_id):
        return 0

    async def _build_context(query, user_id=None):
        return ''

    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [])

    task_id = 'task-stop-1'
    orch._cancelled_tasks.add(task_id)

    events = [
        event async for event in orch.stream(
            query='Stop me',
            user_id='u1',
            max_iterations=2,
            task_id=task_id,
        )
    ]

    assert any(e.type == EventType.STATUS and e.content == 'stopped by user' for e in events)
    assert all(e.type != EventType.DONE for e in events)


async def test_stream_uses_fallback_model_on_model_error(monkeypatch):
    responses = [
        Exception('404 model not found'),
        _response_with_text('Recovered with fallback'),
    ]

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-fallback'

    async def _load_messages(conversation_id):
        return []

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        return None

    async def _save_interaction(**kwargs):
        return None

    async def _build_context(query, user_id=None):
        return ''

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClientWithErrors(responses))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [])
    monkeypatch.setattr(orch.router, 'get_next_fallback', lambda model: 'fallback-model')

    events = [
        event async for event in orch.stream(query='Fallback please', user_id='u1', max_iterations=2)
    ]
    full_text = ''.join((e.content or '') for e in events if e.type == EventType.TEXT_DELTA)

    assert any(e.type == EventType.STATUS and (e.content or '').startswith('using fallback model') for e in events)
    assert 'Recovered with fallback' in full_text


async def test_stream_truncates_large_tool_results(monkeypatch):
    responses = [
        _response_with_tool_call('web_search', '{"query":"huge"}'),
        _response_with_text('Done after tool'),
    ]

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-truncate'

    async def _load_messages(conversation_id):
        return []

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        return None

    async def _save_interaction(**kwargs):
        return None

    async def _build_context(query, user_id=None):
        return ''

    async def _tool_call(name, **kwargs):
        # 2001 lines — exceeds DEFAULT_MAX_LINES (2000)
        return ('x' * 80 + '\n') * 2001

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClient(responses))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [{'type': 'function'}])
    monkeypatch.setattr(orch.tools, 'call', _tool_call)

    events = [
        event async for event in orch.stream(query='Trigger huge tool result', user_id='u1', max_iterations=3)
    ]

    tool_results = [e.tool_result for e in events if e.type == EventType.TOOL_RESULT]
    assert len(tool_results) == 1
    assert 'truncated' in tool_results[0]