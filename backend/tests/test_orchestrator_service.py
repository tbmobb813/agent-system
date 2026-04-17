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


class _RecordingCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _RecordingClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=_RecordingCompletions(response))


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

    # Query must not be "conversational" or "simple" or orchestrator skips memory extraction.
    substantive_query = (
        "Compare the trade-offs between REST and GraphQL for a mobile app "
        "with intermittent connectivity."
    )
    events = [
        event async for event in orch.stream(query=substantive_query, user_id='u1', max_iterations=2)
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


async def test_stream_includes_plan_and_success_criteria_for_first_complex_tool_run(monkeypatch):
    fake_response = _response_with_text('Planned answer')
    recording_client = _RecordingClient(fake_response)

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-plan'

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

    async def _plan(*args, **kwargs):
        return '1. Read docs\n2. Call tools\nDone when: user gets a clear final answer with cited results'

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: recording_client)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [{'type': 'function'}])
    monkeypatch.setattr(orch, '_make_plan', _plan)

    events = [
        event async for event in orch.stream(
            query='Compare two cloud architectures and recommend one',
            user_id='u1',
            max_iterations=2,
        )
    ]

    assert any(e.type == EventType.STATUS and e.content == 'planning...' for e in events)

    assert len(recording_client.chat.completions.calls) == 1
    call = recording_client.chat.completions.calls[0]
    messages = call['messages']
    assert messages[0]['role'] == 'system'
    assert '<success_criteria>' in messages[0]['content']
    assert 'Done when: user gets a clear final answer with cited results' in messages[0]['content']
    assert messages[-1]['role'] == 'user'
    assert messages[-1]['content'].startswith('[Plan]')


async def test_stream_skips_planning_for_followup_with_history(monkeypatch):
    fake_response = _response_with_text('Follow-up answer')

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-follow-up'

    async def _load_messages(conversation_id):
        return [{'role': 'assistant', 'content': 'previous answer'}]

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        return None

    async def _save_interaction(**kwargs):
        return None

    async def _build_context(query, user_id=None):
        return ''

    plan_calls = {'count': 0}

    async def _plan(*args, **kwargs):
        plan_calls['count'] += 1
        return '1. This should not run\nDone when: never'

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClient([fake_response]))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [{'type': 'function'}])
    monkeypatch.setattr(orch, '_make_plan', _plan)

    events = [
        event async for event in orch.stream(
            query='Compare two cloud architectures and recommend one',
            user_id='u1',
            max_iterations=2,
        )
    ]

    assert plan_calls['count'] == 0
    assert all(not (e.type == EventType.STATUS and e.content == 'planning...') for e in events)


async def test_stream_skips_memory_extraction_for_transactional_followup(monkeypatch):
    fake_response = _response_with_text('Updated.')
    saved = {'memory': 0}

    async def _get_or_create(conversation_id, user_id=None):
        return 'conv-follow-up-memory'

    async def _load_messages(conversation_id):
        return [{'role': 'assistant', 'content': 'prior long answer'}]

    async def _estimate_tokens(conversation_id):
        return 0

    async def _save_turn(**kwargs):
        return None

    async def _save_interaction(**kwargs):
        saved['memory'] += 1

    async def _build_context(query, user_id=None):
        return ''

    monkeypatch.setattr('app.agent.orchestrator._openrouter_client', lambda: _FakeClient([fake_response]))
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.get_or_create', _get_or_create)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.load_messages', _load_messages)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.estimate_tokens', _estimate_tokens)
    monkeypatch.setattr('app.agent.orchestrator.conversation_manager.save_turn', _save_turn)
    monkeypatch.setattr('app.agent.orchestrator.memory_manager.save_interaction', _save_interaction)
    monkeypatch.setattr('app.agent.orchestrator.context_builder.build', _build_context)

    orch = AgentOrchestrator(cost_tracker=None)
    monkeypatch.setattr(orch.tools, 'get_tool_schemas', lambda selected=None: [])

    events = [
        event async for event in orch.stream(
            query='Can you make that shorter?',
            user_id='u1',
            max_iterations=2,
        )
    ]

    assert events[-1].type == EventType.DONE
    assert saved['memory'] == 0