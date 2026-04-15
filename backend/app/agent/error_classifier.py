"""
API error classifier for the agent orchestrator.

Translates raw exceptions from the OpenAI-compatible SDK into structured
recovery actions: retry with backoff, rotate model, compress context, or abort.

Replaces the inline string-matching in the orchestrator's except block with a
centralized classifier that returns a typed result the retry loop can act on.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Error taxonomy ────────────────────────────────────────────────────────────

class FailoverReason(enum.Enum):
    # Transient — safe to retry with backoff
    rate_limit    = "rate_limit"     # 429 — throttled, wait then retry/rotate
    overloaded    = "overloaded"     # 503/529 — provider overloaded, backoff
    server_error  = "server_error"   # 500/502 — internal error, retry

    # Transport — rebuild client + retry once
    timeout       = "timeout"

    # Model issues — rotate to next model in fallback chain
    model_not_found   = "model_not_found"    # 404 or invalid model ID
    tool_unsupported  = "tool_unsupported"   # model doesn't support tool calls

    # Context / payload — compress before retry
    context_overflow  = "context_overflow"   # context too large
    payload_too_large = "payload_too_large"  # 413

    # Fatal — abort immediately, surface to user
    auth    = "auth"     # 401/403 — bad API key
    billing = "billing"  # 402 — out of credits
    format_error = "format_error"  # 400 (not tool/context related)

    # Unknown — retry once with backoff, then give up
    unknown = "unknown"


# ── Retry schedule per reason ─────────────────────────────────────────────────

# List of wait-seconds for successive retries (empty = no retry)
RETRY_DELAYS: dict[FailoverReason, list[float]] = {
    FailoverReason.rate_limit:   [5.0, 15.0, 30.0],
    FailoverReason.overloaded:   [3.0, 10.0, 20.0],
    FailoverReason.server_error: [2.0,  5.0, 10.0],
    FailoverReason.timeout:      [0.0],          # immediate retry, once
    FailoverReason.unknown:      [3.0,  8.0],
}

FATAL_REASONS = {
    FailoverReason.auth,
    FailoverReason.billing,
    FailoverReason.format_error,
}


# ── Classification result ─────────────────────────────────────────────────────

@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: Optional[int] = None
    message: str = ""
    retry_delays: list[float] = field(default_factory=list)

    @property
    def is_fatal(self) -> bool:
        return self.reason in FATAL_REASONS

    @property
    def should_rotate_model(self) -> bool:
        return self.reason in (FailoverReason.model_not_found, FailoverReason.tool_unsupported)

    @property
    def should_compress(self) -> bool:
        return self.reason in (FailoverReason.context_overflow, FailoverReason.payload_too_large)

    @property
    def is_retriable(self) -> bool:
        return bool(self.retry_delays) and not self.is_fatal


# ── Classifier ────────────────────────────────────────────────────────────────

# Patterns matched against the lowercased error string
_PATTERNS: list[tuple[re.Pattern, FailoverReason]] = [
    # Auth
    (re.compile(r"401|invalid.{0,20}api.{0,10}key|unauthorized|authentication"), FailoverReason.auth),
    (re.compile(r"403|forbidden"),                                                FailoverReason.auth),

    # Billing
    (re.compile(r"402|insufficient.{0,20}credits|billing|out of credits|payment"), FailoverReason.billing),

    # Rate limit
    (re.compile(r"429|rate.?limit|too many requests|quota"),                      FailoverReason.rate_limit),

    # Overloaded
    (re.compile(r"529|overloaded|capacity|503|service.{0,10}unavailable"),        FailoverReason.overloaded),

    # Server error
    (re.compile(r"500|502|internal.{0,10}server|bad.{0,5}gateway"),               FailoverReason.server_error),

    # Payload
    (re.compile(r"413|payload.{0,10}too.{0,10}large|request.{0,10}too.{0,10}large"), FailoverReason.payload_too_large),

    # Context overflow
    (re.compile(r"context.{0,20}length|maximum.{0,20}token|token.{0,20}limit|"
                r"reduce.{0,20}length|too many tokens|input.{0,20}too.{0,10}long"), FailoverReason.context_overflow),

    # Tool use unsupported
    (re.compile(r"tool.{0,20}not.{0,10}support|does not support.{0,20}tool|"
                r"function.{0,20}call.{0,10}not.{0,10}support"),                  FailoverReason.tool_unsupported),

    # Model not found
    (re.compile(r"404|model.{0,20}not.{0,10}found|no.{0,10}such.{0,10}model|"
                r"invalid.{0,20}model"),                                           FailoverReason.model_not_found),

    # Format error (400 not covered above)
    (re.compile(r"400|bad.{0,10}request|invalid.{0,20}request"),                  FailoverReason.format_error),
]


def classify(exc: Exception) -> ClassifiedError:
    """
    Classify an exception raised by an OpenAI-compatible API call.

    Checks SDK exception types first (most reliable), then falls back to
    regex pattern matching on the string representation.
    """
    # ── Try SDK-typed exceptions first ───────────────────────────────────────
    status_code: Optional[int] = None
    try:
        # openai SDK exceptions carry .status_code
        status_code = getattr(exc, "status_code", None)
    except Exception:
        pass

    exc_type = type(exc).__name__.lower()
    exc_str  = str(exc).lower()

    # Timeout — SDK raises APITimeoutError or asyncio.TimeoutError
    if "timeout" in exc_type or "timeout" in exc_str:
        return _make(FailoverReason.timeout, status_code, exc)

    # Connection error — treat as transient server error
    if "connection" in exc_type or "connect" in exc_str:
        return _make(FailoverReason.server_error, status_code, exc)

    # Status-code–based classification (most precise)
    if status_code is not None:
        sc = int(status_code)
        if sc in (401, 403):
            return _make(FailoverReason.auth, sc, exc)
        if sc == 402:
            return _make(FailoverReason.billing, sc, exc)
        if sc == 404:
            return _make(FailoverReason.model_not_found, sc, exc)
        if sc == 413:
            return _make(FailoverReason.payload_too_large, sc, exc)
        if sc == 429:
            return _make(FailoverReason.rate_limit, sc, exc)
        if sc in (500, 502):
            return _make(FailoverReason.server_error, sc, exc)
        if sc in (503, 529):
            return _make(FailoverReason.overloaded, sc, exc)
        if sc == 400:
            # 400 could be context overflow or bad request — check message
            for pattern, reason in _PATTERNS:
                if pattern.search(exc_str):
                    return _make(reason, sc, exc)
            return _make(FailoverReason.format_error, sc, exc)

    # ── Regex pattern matching on error string ────────────────────────────────
    for pattern, reason in _PATTERNS:
        if pattern.search(exc_str):
            return _make(reason, status_code, exc)

    logger.debug(f"Unclassified error: {exc_type}: {exc_str[:200]}")
    return _make(FailoverReason.unknown, status_code, exc)


def _make(reason: FailoverReason, status_code: Optional[int], exc: Exception) -> ClassifiedError:
    delays = RETRY_DELAYS.get(reason, [])
    msg = str(exc)[:300]
    logger.debug(f"Classified as {reason.value} (HTTP {status_code}): {msg[:120]}")
    return ClassifiedError(
        reason=reason,
        status_code=status_code,
        message=msg,
        retry_delays=list(delays),
    )
