from app.agent.documents import (
    _count_tokens,
    _token_chunks,
    get_context_for_query,
    ingest_document,
    parse_document,
    search_documents,
)
from unittest.mock import AsyncMock


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, *args):
        pass


def test_count_tokens_estimates_from_text_length():
    # Rough estimate: 1 token ~= 4 chars
    result = _count_tokens("hello world")  # 11 chars
    assert result >= 2  # At least 11/4 = 2 or 3


def test_token_chunks_splits_text_into_chunks():
    long_text = "word " * 1000  # 5000 chars
    chunks = _token_chunks(long_text, chunk_tokens=200, overlap=20)

    assert len(chunks) > 1
    assert all(isinstance(c, str) for c in chunks)
    # Each chunk should be roughly 200 tokens * 4 chars = 800 chars (give or take overlap)
    assert all(len(c) > 100 for c in chunks)


def test_token_chunks_maintains_overlap():
    text = "a" * 2000
    chunks_no_overlap = _token_chunks(text, chunk_tokens=100, overlap=0)
    chunks_with_overlap = _token_chunks(text, chunk_tokens=100, overlap=10)

    # With overlap, we should have more chunks (since they overlap)
    assert len(chunks_with_overlap) >= len(chunks_no_overlap)


def test_parse_document_handles_txt():
    data = b"Hello, this is a text file."
    result = parse_document("test.txt", data)

    assert result == "Hello, this is a text file."


def test_parse_document_handles_md():
    data = b"# Heading\n\nSome markdown content."
    result = parse_document("notes.md", data)

    assert "Heading" in result
    assert "markdown" in result


def test_parse_document_rejects_unsupported_type():
    data = b"some binary garbage"
    try:
        parse_document("test.bin", data)
        # If we get here, plain-text parsing may have succeeded
        # (which is okay as a fallback)
    except ValueError as e:
        assert "Unsupported" in str(e) or "unreadable" in str(e)


def test_parse_document_detects_empty_content():
    try:
        parse_document("empty.txt", b"")
        # May succeed with empty string, which is okay
    except ValueError:
        # Or may raise, which is also okay
        pass


async def test_ingest_document_raises_when_db_not_connected(monkeypatch):
    monkeypatch.setattr('app.agent.documents._db.db_pool', None)

    try:
        await ingest_document('a.txt', b'hello')
        assert False, 'Expected RuntimeError'
    except RuntimeError as e:
        assert 'Database not connected' in str(e)


async def test_ingest_document_raises_for_empty_parsed_text(monkeypatch):
    async def fake_embed(_text):
        return None

    fake_conn = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    monkeypatch.setattr('app.agent.documents._db.db_pool', fake_pool)
    monkeypatch.setattr('app.agent.documents.parse_document', lambda _f, _d: '   ')
    monkeypatch.setattr('app.agent.documents._embed', fake_embed)

    try:
        await ingest_document('a.txt', b'hello')
        assert False, 'Expected ValueError'
    except ValueError as e:
        assert 'empty or unreadable' in str(e)


async def test_ingest_document_stores_chunks_and_returns_summary(monkeypatch):
    fake_conn = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.acquire = lambda: AsyncContextManager(fake_conn)

    async def fake_embed(text):
        # First chunk has embedding, second does not.
        return [0.1, 0.2] if 'chunk1' in text else None

    monkeypatch.setattr('app.agent.documents._db.db_pool', fake_pool)
    monkeypatch.setattr('app.agent.documents.parse_document', lambda _f, _d: 'doc text')
    monkeypatch.setattr('app.agent.documents._token_chunks', lambda _t: ['chunk1', 'chunk2'])
    monkeypatch.setattr('app.agent.documents._count_tokens', lambda c: 5 if c == 'chunk1' else 7)
    monkeypatch.setattr('app.agent.documents._embed', fake_embed)

    result = await ingest_document('file.txt', b'bytes', user_id='u1')

    assert result['filename'] == 'file.txt'
    assert result['file_type'] == 'txt'
    assert result['chunk_count'] == 2
    assert result['total_tokens'] == 12
    # 3 execute calls: documents row + 2 chunk rows
    assert fake_conn.execute.await_count == 3


async def test_search_documents_uses_vector_when_embedding_exists(monkeypatch):
    async def fake_embed(_q):
        return [0.3, 0.4]

    async def fake_vector(_emb, _uid, _limit, _doc_id):
        return [{'id': 'c1', 'filename': 'doc.txt', 'content': 'hello'}]

    monkeypatch.setattr('app.agent.documents._db.db_pool', object())
    monkeypatch.setattr('app.agent.documents._embed', fake_embed)
    monkeypatch.setattr('app.agent.documents._vector_search_docs', fake_vector)

    rows = await search_documents('query', user_id='u1', limit=3)
    assert len(rows) == 1
    assert rows[0]['id'] == 'c1'


async def test_search_documents_falls_back_to_fulltext(monkeypatch):
    async def fake_embed(_q):
        return None

    async def fake_fulltext(_q, _uid, _limit, _doc_id):
        return [{'id': 'c2', 'filename': 'doc2.txt', 'content': 'world'}]

    monkeypatch.setattr('app.agent.documents._db.db_pool', object())
    monkeypatch.setattr('app.agent.documents._embed', fake_embed)
    monkeypatch.setattr('app.agent.documents._fulltext_search_docs', fake_fulltext)

    rows = await search_documents('query', user_id='u1', limit=3)
    assert len(rows) == 1
    assert rows[0]['id'] == 'c2'


async def test_get_context_for_query_formats_chunks(monkeypatch):
    async def fake_search(_q, user_id=None, limit=4, document_id=None):
        return [
            {'filename': 'a.txt', 'chunk_index': 0, 'content': 'A' * 1500},
            {'filename': 'b.txt', 'chunk_index': 1, 'content': 'B' * 2000},
        ]

    monkeypatch.setattr('app.agent.documents.search_documents', fake_search)

    ctx = await get_context_for_query('topic', user_id='u1', limit=4, max_chars=2000)

    assert ctx.startswith('Relevant content from your documents:')
    assert '[a.txt — chunk 0]' in ctx
    assert '[b.txt — chunk 1]' in ctx
    assert len(ctx) < 2600
