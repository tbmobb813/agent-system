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


async def test_get_task_detail_returns_feedback(monkeypatch):
    async def fake_fetchrow(query, task_id):
        if 'FROM tasks' in query:
            return {'id': task_id, 'query': 'q1', 'status': 'completed'}
        return {'signal': 'up', 'notes': 'good structure', 'created_at': 'now'}

    async def fake_fetch(_query, _task_id):
        return [{'step_number': 1, 'action': 'search'}]

    monkeypatch.setattr('app.routes.history.fetchrow', fake_fetchrow)
    monkeypatch.setattr('app.routes.history.fetch', fake_fetch)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/history/task-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['feedback']['signal'] == 'up'
    assert payload['steps'][0]['step_number'] == 1


async def test_submit_task_feedback_persists_and_promotes_learning(monkeypatch):
    inserted = {}

    async def fake_fetchrow(query, *args):
        if 'FROM tasks' in query:
            task_id = args[0]
            return {'id': task_id, 'query': 'Summarize this repo', 'user_id': 'default', 'status': 'completed'}
        if 'INSERT INTO task_feedback' in query:
            inserted['task_id'] = args[0]
            inserted['user_id'] = args[1]
            inserted['signal'] = args[2]
            inserted['notes'] = args[3]
            return {'signal': args[2], 'notes': args[3], 'created_at': '2026-01-01T00:00:00Z'}
        return None

    promoted = {}

    async def fake_promote(**kwargs):
        promoted.update(kwargs)
        return 'memory-1'

    monkeypatch.setattr('app.routes.history.fetchrow', fake_fetchrow)
    monkeypatch.setattr('app.routes.history.memory_manager.save_feedback_learning', fake_promote)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/history/task-1/feedback',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            json={'signal': 'down', 'notes': 'too vague'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert inserted['task_id'] == 'task-1'
    assert inserted['signal'] == 'down'
    assert inserted['notes'] == 'too vague'
    assert payload['created_at'] == '2026-01-01T00:00:00Z'
    assert promoted['task_query'] == 'Summarize this repo'
    assert promoted['signal'] == 'down'


async def test_submit_task_feedback_skips_learning_when_notes_blank(monkeypatch):
    async def fake_fetchrow(query, *args):
        if 'FROM tasks' in query:
            task_id = args[0]
            return {'id': task_id, 'query': 'Summarize this repo', 'user_id': 'default', 'status': 'completed'}
        if 'INSERT INTO task_feedback' in query:
            return {'signal': args[2], 'notes': args[3], 'created_at': '2026-01-01T00:00:00Z'}
        return None

    promoted = {'called': False}

    async def fake_promote(**kwargs):
        promoted['called'] = True

    monkeypatch.setattr('app.routes.history.fetchrow', fake_fetchrow)
    monkeypatch.setattr('app.routes.history.memory_manager.save_feedback_learning', fake_promote)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/history/task-1/feedback',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            json={'signal': 'up', 'notes': '   '},
        )

    assert response.status_code == 200
    assert promoted['called'] is False


async def test_submit_task_feedback_rejects_non_completed_task(monkeypatch):
    async def fake_fetchrow(query, *args):
        if 'FROM tasks' in query:
            task_id = args[0]
            return {'id': task_id, 'query': 'Summarize this repo', 'user_id': 'default', 'status': 'running'}
        if 'INSERT INTO task_feedback' in query:
            raise AssertionError('feedback insert should not run for non-completed task')
        return None

    monkeypatch.setattr('app.routes.history.fetchrow', fake_fetchrow)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/history/task-1/feedback',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            json={'signal': 'up', 'notes': 'nice'},
        )

    assert response.status_code == 409
    assert response.json()['detail'] == 'Feedback can only be submitted for completed tasks'
