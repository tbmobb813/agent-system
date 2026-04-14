"""
Authentication and authorization utilities.
"""

import asyncio
import hashlib
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
    Falls back to format-only check if the database is unavailable.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    if not token.startswith("sk-agent-"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Master key bypass — accepts BACKEND_API_KEY and any additional keys in
    # BACKEND_EXTRA_KEYS (comma-separated). Skips DB validation entirely.
    from app.config import settings as app_settings
    allowed = {k.strip() for k in app_settings.BACKEND_API_KEY.split(",") if k.strip()}
    if token in allowed:
        logger.debug(f"API key accepted via master key bypass: {token[:20]}...")
        return token

    # DB validation
    from app.database import db_pool, fetchrow, execute
    if db_pool:
        key_hash = _hash_key(token)
        db_error = False
        try:
            row = await fetchrow(
                "SELECT user_id, is_active FROM api_keys WHERE key_hash = $1",
                key_hash,
            )
        except Exception as e:
            logger.warning(f"API key DB lookup failed: {e} — falling back to format check")
            db_error = True
            row = None

        if not db_error:
            if row is None:
                raise HTTPException(status_code=401, detail="Invalid API key")
            if not row["is_active"]:
                raise HTTPException(status_code=401, detail="API key is disabled")
            # Fire-and-forget last_used update
            asyncio.create_task(
                execute("UPDATE api_keys SET last_used = NOW() WHERE key_hash = $1", key_hash)
            )
            logger.debug(f"API key authenticated (DB): {token[:20]}...")
            return token

    logger.warning(f"API key accepted by format only (no DB): {token[:20]}...")
    return token


def get_user_id_from_key(api_key: str) -> str:
    """
    Extract user ID from API key.
    Format: sk-agent-{user_id}-{random}
    """
    try:
        parts = api_key.split("-")
        if len(parts) >= 3:
            return parts[2]
    except:
        pass
    
    # Fallback to first part of key
    return api_key[:20]


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
