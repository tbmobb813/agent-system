"""
Authentication and authorization utilities.
"""

import asyncio
import hashlib
import hmac
import logging
from fastapi import HTTPException, Header
from typing import Optional

logger = logging.getLogger(__name__)


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Verify API key from Authorization header.

    Expects: Authorization: Bearer sk-agent-xxxxx

    Validates against the api_keys table (key_hash column).

    In production, a working database is required for non-master keys.

    In development, if the DB pool is missing or the lookup errors, a
    format-only check is allowed for local convenience — unless
    ``REQUIRE_DATABASE_API_KEY`` is set (staging / hardened dev), or
    ``ENVIRONMENT`` is ``production``.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    if not token.startswith("sk-agent-"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Master key bypass — accepts any comma-separated key in BACKEND_API_KEY.
    # Skips DB validation entirely.
    from app.config import settings as app_settings
    allowed = [k.strip() for k in app_settings.BACKEND_API_KEY.split(",") if k.strip()]
    for k in allowed:
        if len(k) != len(token):
            continue
        try:
            if hmac.compare_digest(token, k):
                logger.debug("API key accepted via master key bypass")
                return token
        except (TypeError, ValueError):
            continue

    # DB validation
    from app.database import db_pool, fetchrow, execute

    def _format_only_allowed() -> bool:
        if app_settings.REQUIRE_DATABASE_API_KEY:
            return False
        return app_settings.ENVIRONMENT != "production"

    if not db_pool:
        if not _format_only_allowed():
            raise HTTPException(
                status_code=503,
                detail="Database unavailable; API key validation requires a database in production",
            )
        logger.warning("API key accepted by format only (no DB pool configured)")
        return token

    key_hash = _hash_key(token)
    db_error = False
    try:
        row = await fetchrow(
            "SELECT user_id, is_active FROM api_keys WHERE key_hash = $1",
            key_hash,
        )
    except Exception as e:
        logger.warning(f"API key DB lookup failed: {e}")
        db_error = True
        row = None

    if db_error:
        if not _format_only_allowed():
            raise HTTPException(
                status_code=503,
                detail="Unable to validate API key (database error); try again later",
            )
        logger.warning("API key accepted by format only after DB lookup error (development mode)")
        return token

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not row["is_active"]:
        raise HTTPException(status_code=401, detail="API key is disabled")
    # Fire-and-forget last_used update — log but don't fail auth on DB error
    async def _update_last_used():
        try:
            await execute("UPDATE api_keys SET last_used = NOW() WHERE key_hash = $1", key_hash)
        except Exception as e:
            logger.debug(f"Could not update last_used for key: {e}")

    asyncio.create_task(_update_last_used())
    logger.debug("API key authenticated via database")
    return token


def get_user_id_from_key(api_key: str) -> str:
    """
    Return a stable user ID from an API key.
    For the personal agent we always use "default" — there's only one user.
    """
    return "default"


class APIKeyManager:
    """
    Manages API key generation and validation.
    """
    
    @staticmethod
    def generate_key(user_id: str) -> str:
        """Generate a new API key for a user."""
        import secrets
        
        random_suffix = secrets.token_urlsafe(16)
        return f"sk-agent-{user_id}-{random_suffix}"
    
    @staticmethod
    def validate_key(key: str) -> bool:
        """Validate API key format."""
        return key.startswith("sk-agent-") and len(key) > 20
