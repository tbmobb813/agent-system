import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.conversation import ConversationManager


class AsyncContextManager:
    """Helper class that acts as an async context manager for mocking db connections."""
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, *args):
        pass


async def test_get_or_create_returns_provided_id_when_not_none_and_exists(monkeypatch):
    mgr = ConversationManager()

    async def _exists(conv_id):
        return conv_id == 'existing-id'

    monkeypatch.setattr(mgr, '_exists', _exists)

    result = await mgr.get_or_create('existing-id', user_id='u1')

    assert result == 'existing-id'


async def test_get_or_create_generates_new_uuid_when_none_and_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation.db_pool', None)
    mgr = ConversationManager()

    result = await mgr.get_or_create(None, user_id='u1')

    assert result is not None
    assert len(result) == 36  # UUID string length


async def test_load_messages_returns_empty_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation.db_pool', None)
    mgr = ConversationManager()

    messages = await mgr.load_messages('conv-id')

    assert messages == []


async def test_load_messages_shapes_db_rows_to_openai_format(monkeypatch):
    fake_rows = [
        {'role': 'user', 'content': 'Hello'},
        {'role': 'assistant', 'content': 'Hi there'},
    ]

    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(return_value=fake_rows)

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation.db_pool', fake_pool)
    mgr = ConversationManager()

    messages = await mgr.load_messages('conv-id')

    assert len(messages) == 2
    assert messages[0] == {'role': 'user', 'content': 'Hello'}
    assert messages[1] == {'role': 'assistant', 'content': 'Hi there'}


async def test_save_turn_is_noop_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation.db_pool', None)
    mgr = ConversationManager()

    # Should not raise
    await mgr.save_turn(
        'conv-id',
        user_message='hi',
        assistant_message='hello',
    )


async def test_estimate_tokens_counts_stored_tokens_and_falls_back_to_length(monkeypatch):
    fake_rows = [
        {'content': 'a' * 400, 'tokens': 100},  # has stored tokens
        {'content': 'b' * 400, 'tokens': 0},    # no stored, estimate from length
    ]

    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(return_value=fake_rows)

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation.db_pool', fake_pool)
    mgr = ConversationManager()

    total = await mgr.estimate_tokens('conv-id')

    # 100 (stored) + 100 (400/4 from length estimate)
    assert total == 200


async def test_estimate_tokens_returns_0_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation.db_pool', None)
    mgr = ConversationManager()

    total = await mgr.estimate_tokens('conv-id')

    assert total == 0


async def test_delete_conversation_returns_false_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation.db_pool', None)
    mgr = ConversationManager()

    success = await mgr.delete_conversation('conv-id')

    assert success is False
