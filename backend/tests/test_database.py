"""Tests for database module."""

import pytest
from unittest.mock import AsyncMock, patch

from app import database as _db


@pytest.fixture(autouse=True)
def reset_db_pool():
    """Reset db_pool before and after each test."""
    orig_pool = _db.db_pool
    yield
    _db.db_pool = orig_pool


@pytest.mark.asyncio
async def test_get_db_not_initialized():
    """Test get_db raises error when pool not initialized."""
    _db.db_pool = None
    with pytest.raises(RuntimeError, match="Database not initialized"):
        await _db.get_db()


@pytest.mark.asyncio
async def test_get_db_initialized():
    """Test get_db returns pool when initialized."""
    mock_pool = AsyncMock()
    _db.db_pool = mock_pool
    result = await _db.get_db()
    assert result is mock_pool


@pytest.mark.asyncio
async def test_close_db_no_pool():
    """Test close_db when no pool exists."""
    _db.db_pool = None
    await _db.close_db()
    # Should not raise any errors


@pytest.mark.asyncio
async def test_close_db_with_pool():
    """Test close_db closes existing pool."""
    mock_pool = AsyncMock()
    _db.db_pool = mock_pool
    await _db.close_db()
    mock_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_migrations():
    """Test run_migrations executes without error."""
    await _db.run_migrations()


@pytest.mark.asyncio
async def test_execute():
    """Test execute function."""
    mock_conn = AsyncMock()
    mock_acquire_ctx = AsyncMock()
    mock_acquire_ctx.__aenter__.return_value = mock_conn
    mock_acquire_ctx.__aexit__.return_value = None

    with patch.object(_db, "_acquire", return_value=mock_acquire_ctx):
        await _db.execute("SELECT 1", "arg1")
        mock_conn.execute.assert_called_once_with("SELECT 1", "arg1")


@pytest.mark.asyncio
async def test_fetch():
    """Test fetch function."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"id": 1}]
    mock_acquire_ctx = AsyncMock()
    mock_acquire_ctx.__aenter__.return_value = mock_conn
    mock_acquire_ctx.__aexit__.return_value = None

    with patch.object(_db, "_acquire", return_value=mock_acquire_ctx):
        result = await _db.fetch("SELECT *")
        assert result == [{"id": 1}]
        mock_conn.fetch.assert_called_once_with("SELECT *")


@pytest.mark.asyncio
async def test_fetchval():
    """Test fetchval function."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = 42
    mock_acquire_ctx = AsyncMock()
    mock_acquire_ctx.__aenter__.return_value = mock_conn
    mock_acquire_ctx.__aexit__.return_value = None

    with patch.object(_db, "_acquire", return_value=mock_acquire_ctx):
        result = await _db.fetchval("SELECT COUNT(*)")
        assert result == 42
        mock_conn.fetchval.assert_called_once_with("SELECT COUNT(*)")


@pytest.mark.asyncio
async def test_fetchrow():
    """Test fetchrow function."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": 1, "name": "test"}
    mock_acquire_ctx = AsyncMock()
    mock_acquire_ctx.__aenter__.return_value = mock_conn
    mock_acquire_ctx.__aexit__.return_value = None

    with patch.object(_db, "_acquire", return_value=mock_acquire_ctx):
        result = await _db.fetchrow("SELECT * WHERE id = ?", 1)
        assert result == {"id": 1, "name": "test"}
        mock_conn.fetchrow.assert_called_once_with("SELECT * WHERE id = ?", 1)


@pytest.mark.asyncio
async def test_init_db_with_error():
    """Test init_db handles database errors gracefully."""
    with patch("asyncpg.create_pool", side_effect=Exception("Connection failed")):
        await _db.init_db()
        assert _db.db_pool is None


@pytest.mark.asyncio
async def test_init_db_success():
    """Test successful database initialization."""
    mock_pool = AsyncMock()
    # Create an awaitable mock for create_pool
    async def async_create_pool(*args, **kwargs):
        return mock_pool
    
    with patch("asyncpg.create_pool", side_effect=async_create_pool):
        with patch.object(_db, "run_migrations"):
            await _db.init_db()
            assert _db.db_pool is mock_pool


@pytest.mark.asyncio
async def test_reconnect_failure_all_attempts():
    """Test reconnection fails after all attempts."""
    _db.db_pool = None

    with patch("asyncpg.create_pool", side_effect=Exception("Connection failed")):
        result = await _db._reconnect()
        assert result is False


@pytest.mark.asyncio
async def test_acquire_no_pool_raises_error():
    """Test _acquire raises RuntimeError when pool not available."""
    _db.db_pool = None
    with patch.object(_db, "_reconnect", return_value=False):
        with pytest.raises(RuntimeError, match="Database not connected"):
            await _db._acquire()
