from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_get_history_returns_tasks_and_total(monkeypatch):
    async def fake_fetch(_query, _limit, _offset):
        return [{'id': 't1', 'query': 'q1', 'status': 'completed', 'created_at': 'x', 'cost': 0.1, 'model_used': 'm'}]

    async def fake_fetchval(_query):
        return 1

    monkeypatch.setattr('app.routes.history.fetch', fake_fetch)
    monkeypatch.setattr('app.routes.history.fetchval', fake_fetchval)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/history', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 1
    assert payload['tasks'][0]['id'] == 't1'


async def test_get_task_detail_returns_404_when_missing(monkeypatch):
    async def fake_fetchrow(_query, _task_id):
        return None

    monkeypatch.setattr('app.routes.history.fetchrow', fake_fetchrow)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/history/missing', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 404
    assert response.json()['detail'] == 'Task not found'


async def test_delete_task_returns_deleted(monkeypatch):
    calls = {'count': 0}

    async def fake_execute(_query, _task_id):
        calls['count'] += 1
        return None

    monkeypatch.setattr('app.routes.history.execute', fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.delete('/history/task-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    assert response.json() == {'status': 'deleted', 'task_id': 'task-1'}
    assert calls['count'] == 2
