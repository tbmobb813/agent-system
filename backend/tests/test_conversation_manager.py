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
    monkeypatch.setattr('app.agent.conversation._db.db_pool', None)
    mgr = ConversationManager()

    result = await mgr.get_or_create(None, user_id='u1')

    assert result is not None
    assert len(result) == 36  # UUID string length


async def test_load_messages_returns_empty_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation._db.db_pool', None)
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

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    messages = await mgr.load_messages('conv-id')

    assert len(messages) == 2
    assert messages[0] == {'role': 'user', 'content': 'Hello'}
    assert messages[1] == {'role': 'assistant', 'content': 'Hi there'}


async def test_save_turn_is_noop_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation._db.db_pool', None)
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

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    total = await mgr.estimate_tokens('conv-id')

    # 100 (stored) + 100 (400/4 from length estimate)
    assert total == 200


async def test_estimate_tokens_returns_0_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation._db.db_pool', None)
    mgr = ConversationManager()

    total = await mgr.estimate_tokens('conv-id')

    assert total == 0


async def test_delete_conversation_returns_false_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.conversation._db.db_pool', None)
    mgr = ConversationManager()

    success = await mgr.delete_conversation('conv-id')

    assert success is False


async def test_exists_returns_true_when_row_found(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetchval = AsyncMock(return_value='conv-1')

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    exists = await mgr._exists('conv-1')
    assert exists is True


async def test_list_conversations_returns_rows(monkeypatch):
    fake_rows = [
        {
            'id': 'conv-1',
            'user_id': 'u1',
            'created_at': '2026-01-01',
            'updated_at': '2026-01-02',
            'message_count': 4,
        }
    ]

    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(return_value=fake_rows)

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    rows = await mgr.list_conversations(user_id='u1', limit=5)

    assert len(rows) == 1
    assert rows[0]['id'] == 'conv-1'
    assert rows[0]['message_count'] == 4


async def test_compact_deletes_old_messages_and_inserts_summary(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(return_value=[{'id': 'm1'}, {'id': 'm2'}])

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    await mgr.compact('conv-1', 'short summary', keep_recent=1)

    # One fetch for recent ids + two execute calls (delete + insert summary)
    assert fake_conn.fetch.await_count == 1
    assert fake_conn.execute.await_count == 2


async def test_get_or_create_creates_new_when_id_not_found(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.execute = AsyncMock()

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    async def _exists(_conv_id):
        return False

    monkeypatch.setattr(mgr, '_exists', _exists)

    result = await mgr.get_or_create('missing-id', user_id='u1')

    assert result is not None
    assert len(result) == 36
    fake_conn.execute.assert_awaited_once()


async def test_save_turn_persists_and_updates_timestamp(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.executemany = AsyncMock()
    fake_conn.execute = AsyncMock()

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    await mgr.save_turn('conv-1', 'u', 'a', user_tokens=3, assistant_tokens=4)

    fake_conn.executemany.assert_awaited_once()
    fake_conn.execute.assert_awaited_once()


async def test_list_conversations_returns_empty_on_exception(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(side_effect=RuntimeError('boom'))

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    rows = await mgr.list_conversations(user_id='u1')
    assert rows == []


async def test_compact_deletes_all_when_no_recent_ids(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.fetch = AsyncMock(return_value=[])

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    await mgr.compact('conv-1', 'summary', keep_recent=1)

    assert fake_conn.execute.await_count == 2


async def test_delete_conversation_returns_true_with_db(monkeypatch):
    fake_conn = AsyncMock()
    fake_conn.execute = AsyncMock()

    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.conversation._db.db_pool', fake_pool)
    mgr = ConversationManager()

    success = await mgr.delete_conversation('conv-1')

    assert success is True
    fake_conn.execute.assert_awaited_once()
