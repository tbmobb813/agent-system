import asyncio

from fastapi import HTTPException

from app.utils.auth import APIKeyManager, get_user_id_from_key, verify_api_key


async def test_verify_api_key_rejects_missing_authorization():
    try:
        await verify_api_key(None)
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 401
        assert 'Missing authorization header' in e.detail


async def test_verify_api_key_rejects_invalid_bearer_format():
    try:
        await verify_api_key('Token abc')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 401
        assert 'Invalid authorization format' in e.detail


async def test_verify_api_key_rejects_invalid_key_prefix():
    try:
        await verify_api_key('Bearer not-agent-key')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 401
        assert 'Invalid API key format' in e.detail


async def test_verify_api_key_accepts_master_key_bypass(monkeypatch):
    monkeypatch.setattr('app.config.settings.BACKEND_API_KEY', 'sk-agent-master-1,sk-agent-master-2')

    token = await verify_api_key('Bearer sk-agent-master-2')

    assert token == 'sk-agent-master-2'


async def test_verify_api_key_rejects_missing_db_key_when_db_available(monkeypatch):
    async def fake_fetchrow(_query, _key_hash):
        return None

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', fake_fetchrow)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 401
        assert 'Invalid API key' in e.detail


async def test_verify_api_key_rejects_disabled_db_key(monkeypatch):
    async def fake_fetchrow(_query, _key_hash):
        return {'user_id': 'u1', 'is_active': False}

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', fake_fetchrow)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 401
        assert 'disabled' in e.detail


async def test_verify_api_key_accepts_active_db_key_and_schedules_last_used_update(monkeypatch):
    async def fake_fetchrow(_query, _key_hash):
        return {'user_id': 'u1', 'is_active': True}

    async def fake_execute(_query, _key_hash):
        return None

    scheduled = {'count': 0}
    original_create_task = asyncio.create_task

    def fake_create_task(coro):
        scheduled['count'] += 1
        task = original_create_task(coro)
        return task

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', fake_fetchrow)
    monkeypatch.setattr('app.database.execute', fake_execute)
    monkeypatch.setattr('app.utils.auth.asyncio.create_task', fake_create_task)

    token = await verify_api_key('Bearer sk-agent-user-12345')

    assert token == 'sk-agent-user-12345'
    assert scheduled['count'] == 1


async def test_verify_api_key_falls_back_to_format_when_db_lookup_throws(monkeypatch):
    monkeypatch.setattr('app.config.settings.ENVIRONMENT', 'development')

    async def failing_fetchrow(_query, _key_hash):
        raise RuntimeError('db down')

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', failing_fetchrow)

    token = await verify_api_key('Bearer sk-agent-user-12345')

    assert token == 'sk-agent-user-12345'


async def test_verify_api_key_rejects_db_lookup_error_in_production(monkeypatch):
    monkeypatch.setattr('app.config.settings.ENVIRONMENT', 'production')

    async def failing_fetchrow(_query, _key_hash):
        raise RuntimeError('db down')

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', failing_fetchrow)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 503


async def test_verify_api_key_rejects_no_db_pool_in_production(monkeypatch):
    monkeypatch.setattr('app.config.settings.ENVIRONMENT', 'production')
    monkeypatch.setattr('app.database.db_pool', None)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 503


async def test_verify_api_key_rejects_no_db_pool_when_require_database_set(monkeypatch):
    monkeypatch.setattr('app.config.settings.ENVIRONMENT', 'development')
    monkeypatch.setattr('app.config.settings.REQUIRE_DATABASE_API_KEY', True)
    monkeypatch.setattr('app.database.db_pool', None)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 503


async def test_verify_api_key_rejects_db_error_when_require_database_set(monkeypatch):
    monkeypatch.setattr('app.config.settings.ENVIRONMENT', 'development')
    monkeypatch.setattr('app.config.settings.REQUIRE_DATABASE_API_KEY', True)

    async def failing_fetchrow(_query, _key_hash):
        raise RuntimeError('db down')

    monkeypatch.setattr('app.database.db_pool', object())
    monkeypatch.setattr('app.database.fetchrow', failing_fetchrow)

    try:
        await verify_api_key('Bearer sk-agent-user-12345')
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 503


def test_get_user_id_from_key_always_default():
    assert get_user_id_from_key('sk-agent-any') == 'default'


def test_api_key_manager_generate_and_validate():
    key = APIKeyManager.generate_key('u1')

    assert key.startswith('sk-agent-u1-')
    assert APIKeyManager.validate_key(key) is True
    assert APIKeyManager.validate_key('short') is False
