from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_documents_upload_rejects_empty_file():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/documents/upload',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            files={'file': ('empty.txt', b'', 'text/plain')},
        )

    assert response.status_code == 400
    assert response.json()['detail'] == 'Empty file'


async def test_documents_upload_maps_value_error_to_422(monkeypatch):
    async def fake_ingest(filename: str, data: bytes, user_id=None):
        raise ValueError('bad document')

    monkeypatch.setattr('app.routes.documents.ingest_document', fake_ingest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/documents/upload',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            files={'file': ('bad.txt', b'not empty', 'text/plain')},
        )

    assert response.status_code == 422
    assert response.json()['detail'] == 'bad document'


async def test_list_documents_returns_empty_when_db_unavailable(monkeypatch):
    monkeypatch.setattr('app.routes.documents._db.db_pool', None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/documents', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    assert response.json() == {'documents': [], 'total': 0}


async def test_delete_document_returns_404_when_missing(monkeypatch):
    async def fake_fetchrow(_query, _document_id):
        return None

    monkeypatch.setattr('app.routes.documents.fetchrow', fake_fetchrow)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.delete('/documents/doc-1', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 404
    assert response.json()['detail'] == 'Document not found'


async def test_search_documents_route_returns_wrapped_results(monkeypatch):
    async def fake_search(query, limit=5, document_id=None, user_id=None):
        return [{'id': 'c1', 'content': 'hello'}]

    monkeypatch.setattr('app.routes.documents.search_documents', fake_search)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get(
            '/documents/search',
            params={'q': 'hello', 'limit': 1},
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['query'] == 'hello'
    assert payload['total'] == 1
    assert payload['results'][0]['id'] == 'c1'
