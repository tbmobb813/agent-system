from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_endpoint_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert 'timestamp' in payload
    assert isinstance(payload['agent_ready'], bool)
    assert isinstance(payload['cost_tracking'], bool)


async def test_docs_info_endpoint_returns_links():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/docs-info')

    assert response.status_code == 200
    assert response.json() == {'docs': '/redoc', 'openapi': '/openapi.json'}
