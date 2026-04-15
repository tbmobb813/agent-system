from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_list_memories_returns_recent(monkeypatch):
    async def fake_recent(user_id=None, limit=20, category=None):
        return [{'id': 'm1', 'content': 'remember this'}]

    monkeypatch.setattr('app.routes.memory.memory_manager.get_recent', fake_recent)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/memory', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    assert payload['memories'][0]['id'] == 'm1'


async def test_search_memories_returns_results(monkeypatch):
    async def fake_search(query, user_id=None, limit=5, category=None):
        return [{'id': 'm2', 'content': 'search result'}]

    monkeypatch.setattr('app.routes.memory.memory_manager.search', fake_search)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get(
            '/memory/search',
            params={'q': 'result', 'limit': 2},
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['query'] == 'result'
    assert payload['total'] == 1


async def test_save_memory_returns_error_when_save_fails(monkeypatch):
    async def fake_save(content, category='fact', user_id=None, relevance_score=1.0):
        return None

    monkeypatch.setattr('app.routes.memory.memory_manager.save', fake_save)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/memory',
            params={'content': 'x', 'category': 'fact'},
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
        )

    assert response.status_code == 200
    assert response.json() == {'status': 'error', 'detail': 'Database unavailable'}


async def test_delete_memory_returns_deleted_or_error(monkeypatch):
    async def fake_delete(_memory_id):
        return True

    monkeypatch.setattr('app.routes.memory.memory_manager.delete', fake_delete)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.delete('/memory/m-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    assert response.json() == {'status': 'deleted', 'id': 'm-1'}
