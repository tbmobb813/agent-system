"""
Database connection and initialization.
"""

import asyncpg
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

db_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Initialize database connection pool."""
    global db_pool
    
    try:
        db_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("✓ Database pool initialized")
        
        # Run migrations if using local database
        await run_migrations()
    
    except Exception as e:
        logger.warning(f"Database unavailable, running without persistence: {e}")
        db_pool = None


async def run_migrations():
    """Run database migrations (placeholder)."""
    # In production, would run actual SQL migrations
    # For now, assumes database schema already exists
    logger.info("Database migrations checked")


async def close_db():
    """Close database connection pool."""
    global db_pool
    
    if db_pool:
        await db_pool.close()
        logger.info("✓ Database pool closed")


async def get_db() -> asyncpg.Pool:
    """Return the connection pool. Use module-level helpers (fetch, execute, etc.) for queries."""
    global db_pool

    if not db_pool:
        raise RuntimeError("Database not initialized")

    return db_pool


async def execute(query: str, *args):
    """Execute a query."""
    async with db_pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args):
    """Fetch multiple rows."""
    async with db_pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchval(query: str, *args):
    """Fetch a single value."""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def fetchrow(query: str, *args):
    """Fetch a single row."""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(query, *args)
