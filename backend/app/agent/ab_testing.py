"""
A/B Testing — run the same task against two different configurations and
record which approach won on cost, speed, and quality.

Approach configs are dicts with any of:
    model          str   — model ID to use
    system_prompt  str   — extra system prompt text to append
    tools          list  — restrict to these tool names (None = all)

Results are persisted to the `ab_tests` table and retrievable via
GET /analytics/ab-tests.  The winner is determined automatically by
comparing cost and quality (thumbs-up signal via a direct reflection call).

Usage:
    from app.agent.ab_testing import run_ab_test
    result = await run_ab_test(
        task_description="Summarise this article: ...",
        approach_a={"model": "deepseek/deepseek-chat"},
        approach_b={"model": "anthropic/claude-haiku-4-5"},
    )
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app import database as _db

logger = logging.getLogger(__name__)

_MAX_TOKENS = 1024
_QUALITY_JUDGE_MAX_TOKENS = 80


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": "Personal AI Agent",
        },
    )


async def _run_approach(
    task: str,
    model: str,
    extra_system: str = "",
) -> dict:
    """Run a single approach and return a result dict."""
    system = "You are a capable personal AI assistant."
    if extra_system:
        system += f"\n\n{extra_system}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]

    t0 = time.monotonic()
    try:
        resp = await _client().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=_MAX_TOKENS,
            temperature=0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        output = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        # Rough cost estimate from token counts (no per-model pricing table needed)
        cost_estimate = (input_tokens * 0.000001) + (output_tokens * 0.000002)
        return {
            "success": True,
            "output": output,
            "output_preview": output[:300],
            "time_ms": elapsed_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost_estimate,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(f"AB approach failed ({model}): {e}")
        return {
            "success": False,
            "output": "",
            "output_preview": "",
            "time_ms": elapsed_ms,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
            "error": str(e)[:200],
        }


async def _judge_quality(task: str, output_a: str, output_b: str) -> Optional[str]:
    """Ask the cheap model which output better answers the task. Returns 'a', 'b', or 'tie'."""
    prompt = (
        f"Task: {task[:300]}\n\n"
        f"Output A: {output_a[:400]}\n\n"
        f"Output B: {output_b[:400]}\n\n"
        "Which output better answers the task? Reply with exactly one word: A, B, or TIE."
    )
    try:
        resp = await _client().chat.completions.create(
            model=settings.DEFAULT_MODEL_SIMPLE,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_QUALITY_JUDGE_MAX_TOKENS,
            temperature=0,
        )
        verdict = (resp.choices[0].message.content or "").strip().upper()
        if verdict.startswith("A"):
            return "a"
        if verdict.startswith("B"):
            return "b"
        return "tie"
    except Exception as e:
        logger.debug(f"Quality judge failed: {e}")
        return None


async def run_ab_test(
    task_description: str,
    approach_a: dict,
    approach_b: dict,
) -> dict:
    """
    Run task_description against both approaches in parallel, compare results,
    persist to `ab_tests`, and return the full comparison dict.

    approach_a / approach_b keys:
        model          str  (required)
        system_prompt  str  (optional extra system text)
    """
    model_a = approach_a.get("model", settings.DEFAULT_MODEL_SIMPLE)
    model_b = approach_b.get("model", settings.DEFAULT_MODEL_SIMPLE)
    sys_a = approach_a.get("system_prompt", "")
    sys_b = approach_b.get("system_prompt", "")

    result_a, result_b = await asyncio.gather(
        _run_approach(task_description, model_a, sys_a),
        _run_approach(task_description, model_b, sys_b),
    )

    # Determine winner
    winner: Optional[str] = None
    win_reason: Optional[str] = None

    if not result_a["success"] and result_b["success"]:
        winner, win_reason = "b", "availability"
    elif result_a["success"] and not result_b["success"]:
        winner, win_reason = "a", "availability"
    elif result_a["success"] and result_b["success"]:
        # Compare on three dimensions
        quality_winner = await _judge_quality(
            task_description, result_a["output"], result_b["output"]
        )
        cost_winner = "a" if result_a["cost"] <= result_b["cost"] else "b"
        speed_winner = "a" if result_a["time_ms"] <= result_b["time_ms"] else "b"

        votes = {"a": 0, "b": 0}
        for w in [quality_winner, cost_winner, speed_winner]:
            if w in votes:
                votes[w] += 1

        if votes["a"] > votes["b"]:
            winner, win_reason = "a", "overall"
        elif votes["b"] > votes["a"]:
            winner, win_reason = "b", "overall"
        else:
            winner, win_reason = "tie", "overall"

        # Prefer more specific reason when one dimension is decisive
        if quality_winner == cost_winner == speed_winner:
            win_reason = "cost+quality+speed"
        elif quality_winner == winner:
            win_reason = "quality"
        elif cost_winner == winner:
            win_reason = "cost"

    if _db.db_pool:
        try:
            await _db.execute(
                """
                INSERT INTO ab_tests
                    (task_description, approach_a, approach_b,
                     result_a, result_b, winner, win_reason)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                task_description[:500],
                json.dumps({**approach_a, "model": model_a}),
                json.dumps({**approach_b, "model": model_b}),
                json.dumps({k: v for k, v in result_a.items() if k != "output"}),
                json.dumps({k: v for k, v in result_b.items() if k != "output"}),
                winner,
                win_reason,
            )
        except Exception as e:
            logger.debug(f"AB test DB insert failed: {e}")

    return {
        "task": task_description[:200],
        "approach_a": {**approach_a, "model": model_a},
        "approach_b": {**approach_b, "model": model_b},
        "result_a": result_a,
        "result_b": result_b,
        "winner": winner,
        "win_reason": win_reason,
    }
