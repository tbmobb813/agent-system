from app.agent.context_builder import ContextBuilder, _token_estimate


def test_token_estimate_uses_chars_per_token_ratio():
    assert _token_estimate('abcd') == 1
    assert _token_estimate('abcdefgh') == 2


async def test_build_returns_empty_when_no_memory_or_docs(monkeypatch):
    async def fake_memory_search(query, user_id=None, limit=4, category=None):
        return []

    async def fake_doc_search(query, user_id=None, limit=4, document_id=None):
        return []

    monkeypatch.setattr('app.agent.memory.memory_manager.search', fake_memory_search)
    monkeypatch.setattr('app.agent.documents.search_documents', fake_doc_search)

    builder = ContextBuilder(max_tokens=1000)
    result = await builder.build('nothing')

    assert result == ''


async def test_build_includes_memory_and_document_sections(monkeypatch):
    async def fake_memory_search(query, user_id=None, limit=4, category=None):
        return [
            {'category': 'preference', 'content': 'User prefers concise responses.'},
            {'category': 'fact', 'content': 'User works on agent-system.'},
        ]

    async def fake_doc_search(query, user_id=None, limit=4, document_id=None):
        return [
            {
                'filename': 'guide.md',
                'chunk_index': 1,
                'content': 'Project setup documentation chunk.',
            }
        ]

    monkeypatch.setattr('app.agent.memory.memory_manager.search', fake_memory_search)
    monkeypatch.setattr('app.agent.documents.search_documents', fake_doc_search)

    builder = ContextBuilder(max_tokens=1000)
    result = await builder.build('project setup', user_id='u1')

    assert '[Memory' in result
    assert '[Documents' in result
    assert '[preference] User prefers concise responses.' in result
    assert 'guide.md' in result
    assert 'chunk 1' in result


async def test_build_respects_budget_and_truncates(monkeypatch):
    async def fake_memory_search(query, user_id=None, limit=4, category=None):
        return [
            {'category': 'fact', 'content': 'A' * 500},
        ]

    async def fake_doc_search(query, user_id=None, limit=4, document_id=None):
        return [
            {
                'filename': 'big.txt',
                'chunk_index': 0,
                'content': 'B' * 500,
            }
        ]

    monkeypatch.setattr('app.agent.memory.memory_manager.search', fake_memory_search)
    monkeypatch.setattr('app.agent.documents.search_documents', fake_doc_search)

    # 100 tokens * 10% * 4 chars ~= 40 char budget
    builder = ContextBuilder(max_tokens=100)
    result = await builder.build('truncate me')

    assert result
    assert len(result) < 250


def test_has_docs_reflects_presence_of_chunks():
    builder = ContextBuilder(max_tokens=100)
    assert builder.has_docs([]) is False
    assert builder.has_docs([{'id': 'x'}]) is True
