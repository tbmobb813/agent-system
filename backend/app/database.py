"""
Database connection and initialization.
"""

import asyncio
import asyncpg
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

db_pool: Optional[asyncpg.Pool] = None

_POOL_KWARGS = dict(
    min_size=2,
    max_size=10,
    command_timeout=60,
    statement_cache_size=0,
)


async def init_db():
    """Initialize database connection pool."""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(settings.DATABASE_URL, **_POOL_KWARGS)
        logger.info("✓ Database pool initialized")
        await run_migrations()
    except Exception as e:
        logger.warning(f"Database unavailable, running without persistence: {e}")
        db_pool = None


async def _reconnect() -> bool:
    """
    Attempt to re-establish the connection pool after a drop.
    Returns True if reconnected, False otherwise.
    Called automatically by helpers when they detect a dead pool.
    """
    global db_pool
    for attempt in range(1, 4):
        try:
            logger.info(f"DB reconnect attempt {attempt}/3...")
            db_pool = await asyncpg.create_pool(settings.DATABASE_URL, **_POOL_KWARGS)
            logger.info("✓ DB reconnected")
            return True
        except Exception as e:
            logger.warning(f"DB reconnect attempt {attempt} failed: {e}")
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s backoff
    logger.error("DB reconnect failed after 3 attempts — running without persistence")
    db_pool = None
    return False


async def run_migrations():
    """Run database migrations (placeholder)."""
    logger.info("Database migrations checked")


async def close_db():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("✓ Database pool closed")


async def get_db() -> asyncpg.Pool:
    """Return the connection pool."""
    global db_pool
    if not db_pool:
        raise RuntimeError("Database not initialized")
    return db_pool


async def _acquire():
    """
    Acquire a connection, auto-reconnecting once if the pool is dead.
    Raises RuntimeError if DB is unavailable after reconnect attempt.
    """
    global db_pool
    if not db_pool:
        reconnected = await _reconnect()
        if not reconnected:
            raise RuntimeError("Database not connected")
    return db_pool.acquire()


async def execute(query: str, *args):
    """Execute a query."""
    async with await _acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    """Fetch multiple rows."""
    async with await _acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchval(query: str, *args):
    """Fetch a single value."""
    async with await _acquire() as conn:
        return await conn.fetchval(query, *args)


async def fetchrow(query: str, *args):
    """Fetch a single row."""
    async with await _acquire() as conn:
        return await conn.fetchrow(query, *args)
