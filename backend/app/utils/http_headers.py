"""Sanitize HTTP response headers before returning them to the LLM agent."""

from __future__ import annotations

from typing import Mapping

# Case-insensitive match against these names (HTTP headers are case-insensitive).
_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "set-cookie",
        "set-cookie2",
        "www-authenticate",
        "x-access-token",
        "x-amz-cf-id",
        "x-amz-security-token",
        "x-api-key",
        "x-auth-token",
        "x-supabase-authorization",
    }
)


def redact_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """
    Return a shallow copy of headers with sensitive values replaced.

    Prevents session cookies, auth tokens, and similar material from being
    embedded in tool output shown to the model.
    """
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADER_NAMES:
            out[key] = "[redacted]"
        else:
            if isinstance(value, bytes):
                out[key] = str(value, "utf-8", errors="replace")
            else:
                out[key] = str(value)
    return out
