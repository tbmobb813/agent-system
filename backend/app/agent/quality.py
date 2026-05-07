"""
Sampled response-quality scoring using a judge LLM.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.database import execute
from app import database as _db

logger = logging.getLogger(__name__)

# Keep defaults local so we can ship this without environment changes.
QUALITY_SCORING_ENABLED = True
QUALITY_SCORING_SAMPLE_RATE = 0.10
QUALITY_SCORING_MODEL = "anthropic/claude-3.5-haiku"


def _judge_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": "Personal AI Agent - Quality Scoring",
        },
    )


def _should_sample() -> bool:
    if not QUALITY_SCORING_ENABLED:
        return False
    if not settings.OPENROUTER_API_KEY:
        return False
    return random.random() <= QUALITY_SCORING_SAMPLE_RATE


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    # Try strict parse first.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: parse first {...} object in response.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def score_response_quality(
    *,
    query: str,
    response: str,
    task_id: Optional[str],
    user_id: Optional[str],
    model_used: Optional[str],
) -> None:
    """Judge a completed answer and store scores in response_quality (best effort)."""
    if not _should_sample():
        return
    if not response.strip():
        return

    prompt = (
        "You are an impartial evaluator for assistant responses.\n"
        "Score each dimension from 1 to 5 (integer only):\n"
        "- helpfulness\n"
        "- accuracy\n"
        "- conciseness\n"
        "- tool_usage_appropriateness\n"
        "Then provide:\n"
        "- overall_score (1-5 integer)\n"
        "- rationale (max 240 chars)\n\n"
        "Return STRICT JSON only with keys:\n"
        "{\"helpfulness\":int,\"accuracy\":int,\"conciseness\":int,"
        "\"tool_usage_appropriateness\":int,\"overall_score\":int,\"rationale\":string}\n\n"
        f"User query:\n{query}\n\nAssistant response:\n{response}"
    )

    try:
        client = _judge_client()
        resp = await client.chat.completions.create(
            model=QUALITY_SCORING_MODEL,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = _extract_json_object(content)
        if not data:
            logger.debug("Quality scorer returned non-JSON output")
            return

        helpfulness = int(data.get("helpfulness", 0))
        accuracy = int(data.get("accuracy", 0))
        conciseness = int(data.get("conciseness", 0))
        tool_usage = int(data.get("tool_usage_appropriateness", 0))
        overall = int(data.get("overall_score", 0))
        rationale = str(data.get("rationale", ""))[:240]

        # Basic bounds clamp to keep downstream queries sane.
        def _clamp(v: int) -> int:
            return max(1, min(5, v))

        helpfulness = _clamp(helpfulness)
        accuracy = _clamp(accuracy)
        conciseness = _clamp(conciseness)
        tool_usage = _clamp(tool_usage)
        overall = _clamp(overall)

        if not _db.db_pool:
            return
        await execute(
            """
            INSERT INTO response_quality (
                task_id, user_id, model_used, helpfulness, accuracy, conciseness,
                tool_usage_appropriateness, overall_score, rationale, query, response, created_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW())
            """,
            task_id,
            user_id,
            model_used,
            helpfulness,
            accuracy,
            conciseness,
            tool_usage,
            overall,
            rationale,
            query[:2000],
            response[:8000],
        )
    except Exception as e:
        logger.debug(f"Quality scoring skipped/failed: {e}")
