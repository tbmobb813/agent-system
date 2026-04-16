from httpx import ASGITransport, AsyncClient
import builtins

import app.routes.settings as settings_routes

from app.main import app


async def test_get_settings_returns_defaults_when_store_empty(monkeypatch):
    monkeypatch.setattr('app.routes.settings._load', lambda: {})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/settings', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['max_monthly_cost'] == 30.0
    assert payload['timezone'] == 'UTC'
    assert payload['agent_persona_enabled'] is True
    assert payload['agent_persona_path'] == 'data/persona'


async def test_get_settings_returns_saved_values(monkeypatch):
    monkeypatch.setattr(
        'app.routes.settings._load',
        lambda: {
            'preferred_model': 'deepseek/deepseek-chat',
            'max_monthly_cost': 75.0,
            'enable_notifications': False,
            'auto_save_results': False,
            'timezone': 'America/New_York',
            'agent_persona_enabled': False,
            'agent_persona_path': 'backend/data/persona',
            'metadata': {},
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/settings', headers={'Authorization': 'Bearer sk-agent-local-dev'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['preferred_model'] == 'deepseek/deepseek-chat'
    assert payload['max_monthly_cost'] == 75.0


async def test_update_settings_persists_and_returns_updated(monkeypatch):
    captured = {}

    def fake_save(data):
        captured['data'] = data

    monkeypatch.setattr('app.routes.settings._save', fake_save)

    body = {
        'preferred_model': 'deepseek/deepseek-chat',
        'max_monthly_cost': 45.0,
        'enable_notifications': True,
        'auto_save_results': True,
        'context_window_target_percent': 0.75,
        'default_tools': ['web_search'],
        'timezone': 'UTC',
        'agent_persona_enabled': True,
        'agent_persona_path': 'data/persona',
        'metadata': {'env': 'test'},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post(
            '/settings',
            headers={'Authorization': 'Bearer sk-agent-local-dev'},
            json=body,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'updated'
    assert captured['data']['max_monthly_cost'] == 45.0
    assert captured['data']['agent_persona_enabled'] is True
    assert payload['settings']['preferred_model'] == 'deepseek/deepseek-chat'


def test_load_returns_empty_dict_when_file_missing(monkeypatch):
    def raise_missing(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(builtins, 'open', raise_missing)

    assert settings_routes._load() == {}


def test_save_swallows_io_errors(monkeypatch):
    def raise_io(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(builtins, 'open', raise_io)

    # Should not raise even if writing fails
    settings_routes._save({'a': 1})
