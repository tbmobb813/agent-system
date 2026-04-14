from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_list_conversations_returns_items(monkeypatch):
    async def fake_list(user_id=None, limit=20):
        return [{'id': 'conv-1'}, {'id': 'conv-2'}]

    monkeypatch.setattr('app.routes.conversations.conversation_manager.list_conversations', fake_list)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/conversations', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == 2
    assert payload['conversations'][0]['id'] == 'conv-1'


async def test_get_conversation_returns_messages(monkeypatch):
    async def fake_load(conversation_id, max_turns=50):
        return [
            {'role': 'user', 'content': 'hi'},
            {'role': 'assistant', 'content': 'hello'},
        ]

    monkeypatch.setattr('app.routes.conversations.conversation_manager.load_messages', fake_load)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/conversations/conv-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['conversation_id'] == 'conv-1'
    assert payload['total'] == 2


async def test_delete_conversation_maps_success_and_error(monkeypatch):
    async def fake_delete_ok(_conversation_id):
        return True

    monkeypatch.setattr('app.routes.conversations.conversation_manager.delete_conversation', fake_delete_ok)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        ok_response = await client.delete('/conversations/conv-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert ok_response.status_code == 200
    assert ok_response.json()['status'] == 'deleted'

    async def fake_delete_fail(_conversation_id):
        return False

    monkeypatch.setattr('app.routes.conversations.conversation_manager.delete_conversation', fake_delete_fail)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        err_response = await client.delete('/conversations/conv-2', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert err_response.status_code == 200
    assert err_response.json()['status'] == 'error'
