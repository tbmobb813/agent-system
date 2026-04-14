from unittest.mock import AsyncMock

from app.agent.memory import MemoryManager, _classify_insight


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, *args):
        pass


def test_classify_insight_recognizes_preference_keywords():
    assert _classify_insight("user prefers Python to JavaScript") == "preference"
    assert _classify_insight("user likes dark mode") == "preference"
    assert _classify_insight("user wants concise answers") == "preference"


def test_classify_insight_recognizes_pattern_keywords():
    assert _classify_insight("user always uses async code") == "pattern"
    assert _classify_insight("user never works on weekends") == "pattern"
    assert _classify_insight("user usually asks for examples") == "pattern"


def test_classify_insight_recognizes_fact_keywords():
    assert _classify_insight("my project is called ReGrabber") == "fact"
    assert _classify_insight("i'm a software engineer") == "fact"
    assert _classify_insight("i am building an app") == "fact"


def test_classify_insight_defaults_to_fact_for_unknown():
    assert _classify_insight("some random text") == "fact"
    assert _classify_insight("hello world") == "fact"


async def test_save_returns_none_when_no_db(monkeypatch):
    monkeypatch.setattr('app.agent.memory._db.db_pool', None)
    mgr = MemoryManager()

    result = await mgr.save('remember this')

    assert result is None


async def test_save_persists_memory_with_embedding(monkeypatch):
    fake_conn = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    async def fake_embed(_text):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr('app.agent.memory._db.db_pool', fake_pool)
    monkeypatch.setattr('app.agent.memory._embed', fake_embed)

    mgr = MemoryManager()
    memory_id = await mgr.save('user prefers python', category='preference', user_id='u1')

    assert memory_id is not None
    assert len(memory_id) == 36
    assert fake_conn.execute.await_count == 1


async def test_search_uses_vector_path_when_embedding_available(monkeypatch):
    mgr = MemoryManager()

    async def fake_embed(_q):
        return [0.9, 0.8]

    async def fake_vector(_emb, _uid, _limit, _cat):
        return [{'id': 'm1', 'category': 'fact', 'content': 'x', 'similarity': 0.9}]

    monkeypatch.setattr('app.agent.memory._db.db_pool', object())
    monkeypatch.setattr('app.agent.memory._embed', fake_embed)
    monkeypatch.setattr(mgr, '_vector_search', fake_vector)

    rows = await mgr.search('query', user_id='u1', limit=3)

    assert len(rows) == 1
    assert rows[0]['id'] == 'm1'


async def test_search_falls_back_to_fulltext_when_no_embedding(monkeypatch):
    mgr = MemoryManager()

    async def fake_embed(_q):
        return None

    async def fake_fulltext(_q, _uid, _limit, _cat):
        return [{'id': 'm2', 'category': 'context', 'content': 'y', 'similarity': 0.5}]

    monkeypatch.setattr('app.agent.memory._db.db_pool', object())
    monkeypatch.setattr('app.agent.memory._embed', fake_embed)
    monkeypatch.setattr(mgr, '_fulltext_search', fake_fulltext)

    rows = await mgr.search('query', user_id='u1', limit=2)

    assert len(rows) == 1
    assert rows[0]['id'] == 'm2'


async def test_get_context_for_query_formats_and_truncates(monkeypatch):
    mgr = MemoryManager()

    async def fake_search(_query, user_id=None, limit=4, category=None):
        return [
            {'category': 'fact', 'content': 'A' * 1200},
            {'category': 'preference', 'content': 'B' * 1200},
        ]

    monkeypatch.setattr(mgr, 'search', fake_search)

    context = await mgr.get_context_for_query('anything', user_id='u1', limit=4)

    assert context.startswith('Relevant context from past interactions:')
    assert '[fact]' in context
    assert '[preference]' in context
    # MAX_CONTEXT_CHARS guard should keep this bounded.
    assert len(context) < 2000


async def test_save_interaction_skips_when_no_insight(monkeypatch):
    mgr = MemoryManager()

    async def fake_extract(_q, _r):
        return None

    save_mock = AsyncMock()
    monkeypatch.setattr('app.agent.memory._extract_insight', fake_extract)
    monkeypatch.setattr(mgr, 'save', save_mock)

    await mgr.save_interaction('q', 'r', user_id='u1')

    save_mock.assert_not_awaited()


async def test_delete_returns_true_with_db(monkeypatch):
    fake_conn = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)
    monkeypatch.setattr('app.agent.memory._db.db_pool', fake_pool)

    mgr = MemoryManager()
    ok = await mgr.delete('memory-1')

    assert ok is True
    fake_conn.execute.assert_awaited_once()
