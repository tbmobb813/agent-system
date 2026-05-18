"""
Agent Orchestrator - ReAct loop (Reason + Act).

Flow:
  1. LLM receives the user query + available tool schemas.
  2. If LLM wants to call a tool → execute it, feed result back.
  3. Repeat until LLM produces a plain text response (no tool calls).
  4. Stream the final response token-by-token.
"""

import asyncio
import json
import re
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from app.config import settings
from app import database as _db
from app.models import ExecutionEvent, EventType, TaskStatus
from app.utils.truncate import truncate_tail
from app.agent.router import ModelRouter
from app.agent.memory import memory_manager
from app.agent.conversation import conversation_manager
from app.agent.context_builder import context_builder
from app.agent.error_classifier import classify, FailoverReason
from app.tools.tool_registry import ToolRegistry
from app.utils.persona_loader import build_persona_prompt
from app.utils.settings_store import load_settings_dict
from app.agent import decision_tracker
from app.agent.reflection import post_task_reflection
from app.agent import skill_registry
from app.agent.tool_learning import get_tool_hint, learn_tool_chains
from app.agent.cost_learning import refresh_efficiency_cache
from app.agent.prompts.system_prompt import PROMPT_VERSION, build_system_prompt


def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": settings.SITE_URL,
            "X-Title": "Personal AI Agent",
        },
    )


def _openrouter_reasoning_extra_body(
    reasoning_effort: Optional[str],
) -> Optional[dict[str, Any]]:
    """Build OpenRouter `extra_body.reasoning` for chat.completions.
    ``reasoning_effort`` comes from the HTTP request (already normalized).
    ``None`` means inherit ``OPENROUTER_REASONING_EFFORT`` from settings.
    ``\"off\"`` forces no reasoning effort block (overrides env).
    """
    if reasoning_effort is None:
        env = getattr(settings, "OPENROUTER_REASONING_EFFORT", None)
        if env and str(env).strip():
            return {"reasoning": {"effort": str(env).strip().lower()}}
        return None
    if reasoning_effort == "off":
        return None
    return {"reasoning": {"effort": reasoning_effort}}


logger = logging.getLogger(__name__)


def _reasoning_delta_snippet(delta: Any) -> Optional[str]:
    """Readable reasoning from a chat completion stream delta (OpenRouter reasoning_details / reasoning)."""
    parts: list[str] = []
    raw_r = getattr(delta, "reasoning", None)
    if isinstance(raw_r, str) and raw_r.strip():
        parts.append(raw_r)
    details = getattr(delta, "reasoning_details", None)
    if details is not None:
        if isinstance(details, dict):
            details_list: list[Any] = [details]
        elif isinstance(details, list):
            details_list = details
        else:
            details_list = []
        for item in details_list:
            if not isinstance(item, dict):
                continue
            typ = str(item.get("type") or "")
            if typ == "reasoning.text":
                t = item.get("text")
                if isinstance(t, str) and t:
                    parts.append(t)
            elif typ == "reasoning.summary":
                s = item.get("summary")
                if isinstance(s, str) and s:
                    parts.append(s)
    out = "".join(parts)
    return out.strip() or None


@dataclass
class PlanResult:
    """Structured output from the planning step (cheap model)."""

    plan_markdown: str
    plan_confidence: float  # 0.0–1.0
    fallback_if_wrong: str = ""
    risk_notes: str = ""


def _coerce_plan_confidence(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.5
    if x > 1.0:
        x = x / 100.0
    return max(0.0, min(1.0, x))


def _parse_plan_llm_output(raw: str) -> PlanResult:
    """Parse JSON plan from model output; fall back to treating the whole reply as plan_markdown."""
    raw = (raw or "").strip()
    if not raw:
        return PlanResult("", 0.45, "", "")

    def _from_dict(data: dict[str, Any]) -> PlanResult:
        md = str(data.get("plan_markdown") or "").strip()
        if not md:
            md = raw
        return PlanResult(
            plan_markdown=md,
            plan_confidence=_coerce_plan_confidence(data.get("plan_confidence", 50)),
            fallback_if_wrong=str(data.get("fallback_if_wrong") or "").strip(),
            risk_notes=str(data.get("risk_notes") or "").strip(),
        )

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return _from_dict(data)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return _from_dict(data)
        except json.JSONDecodeError:
            pass

    return PlanResult(
        plan_markdown=raw, plan_confidence=0.5, fallback_if_wrong="", risk_notes=""
    )


def _extract_done_when_line(plan_markdown: str) -> Optional[str]:
    for line in (plan_markdown or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("done when:"):
            return stripped
    return None


def _format_progress_checkpoint(state: "ExecutionState") -> str:
    """Summarize in-flight execution for goal alignment (only when there is tool-round memory)."""
    if not state.working_memory:
        return ""

    lines: list[str] = []
    if state.goal:
        lines.append(f"User goal: {state.goal}")
    if state.done_when:
        lines.append(f"Success criterion: {state.done_when}")

    lines.append("Recent trace (most recent last):")
    for entry in state.working_memory[-8:]:
        it = entry.get("iteration", "?")
        typ = entry.get("type", "")
        if typ == "planned_tool_call":
            raw_args = entry.get("args") or {}
            arg_keys = list(raw_args.keys()) if isinstance(raw_args, dict) else []
            lines.append(
                f"  - Round {it}: planned tool {entry.get('tool')} with args {arg_keys}"
            )
        elif typ == "tool_result":
            prev = (entry.get("result_preview") or "")[:160]
            lines.append(
                f"  - Round {it}: {entry.get('tool')} result preview: {prev!r}"
            )
        elif typ == "tool_error":
            lines.append(
                f"  - Round {it}: {entry.get('tool')} error: {entry.get('error')}"
            )
        else:
            lines.append(f"  - Round {it}: {entry}")

    lines.append(
        "Assess progress toward the success criterion. If blocked or off-track, adjust your approach "
        "or ask one clarifying question — do not continue blindly."
    )
    return "\n".join(lines)


def _compose_system_with_progress(system_base: str, state: "ExecutionState") -> str:
    body = _format_progress_checkpoint(state)
    if not body:
        return system_base
    return f"{system_base}\n\n<progress_checkpoint>\n{body}\n</progress_checkpoint>"


class ExecutionState(BaseModel):
    task_id: str
    status: TaskStatus
    current_step: int
    total_steps: int
    results: dict = Field(default_factory=dict)
    errors: list = Field(default_factory=list)
    working_memory: list[dict[str, Any]] = Field(default_factory=list)
    goal: Optional[str] = None
    done_when: Optional[str] = None
    start_time: datetime
    last_update: datetime


class AgentOrchestrator:
    def __init__(self, cost_tracker=None):
        self.cost_tracker = cost_tracker
        self.router = ModelRouter()
        self.tools = ToolRegistry()
        self.active_tasks = {}
        self._cancelled_tasks: set[str] = set()
        self._active_conversations: dict[str, str] = {}  # conv_id → task_id
        self._circuit_failure_threshold = 5
        self._circuit_recovery_seconds = 60
        self._circuit_failures = 0
        self._circuit_open_until: Optional[datetime] = None

    def _is_circuit_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        return datetime.utcnow() < self._circuit_open_until

    def _record_circuit_failure(self) -> None:
        self._circuit_failures += 1
        if self._circuit_failures >= self._circuit_failure_threshold:
            self._circuit_open_until = datetime.utcnow() + timedelta(
                seconds=self._circuit_recovery_seconds
            )

    def _record_circuit_success(self) -> None:
        self._circuit_failures = 0
        self._circuit_open_until = None

    async def run(
        self,
        query: str,
        context: Optional[str] = None,
        tools: Optional[list[str]] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        conversation_id: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        images: Optional[list[str]] = None,
    ) -> tuple[str, Optional[str]]:
        """Execute agent synchronously. Returns (result, conversation_id)."""
        task_id = str(uuid.uuid4())
        result = ""
        final_conversation_id = conversation_id
        async for event in self.stream(
            query=query,
            context=context,
            tools=tools,
            user_id=user_id,
            max_iterations=max_iterations,
            task_id=task_id,
            conversation_id=conversation_id,
            reasoning_effort=reasoning_effort,
            images=images,
        ):
            if event.type == EventType.TEXT_DELTA:
                result += event.content or ""
            if event.type == EventType.DONE and event.conversation_id:
                final_conversation_id = event.conversation_id
        return result, final_conversation_id

    async def stream(
        self,
        query: str,
        context: Optional[str] = None,
        tools: Optional[list[str]] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        task_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        images: Optional[list[str]] = None,
    ) -> AsyncIterator[ExecutionEvent]:
        """
        ReAct loop — stream events as the agent reasons and acts.
        """
        task_id = task_id or str(uuid.uuid4())
        state = ExecutionState(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            current_step=0,
            total_steps=max_iterations,
            goal=query,
            start_time=datetime.utcnow(),
            last_update=datetime.utcnow(),
        )
        self.active_tasks[task_id] = state

        try:
            tool_schemas = self.tools.get_tool_schemas(tools)

            # ── Round 1: fully independent startup work in parallel ───────────
            # get_spent_month, get_or_create, and context retrieval have no
            # dependencies on each other — run them concurrently to minimize
            # time-to-first-token.
            async def _get_budget() -> float:
                if not self.cost_tracker:
                    return settings.OPENROUTER_BUDGET_MONTHLY
                try:
                    spent = await self.cost_tracker.get_spent_month()
                    return settings.OPENROUTER_BUDGET_MONTHLY - spent
                except Exception:
                    return settings.OPENROUTER_BUDGET_MONTHLY

            async def _get_settings() -> dict:
                return await asyncio.to_thread(load_settings_dict)

            (
                budget_remaining,
                conversation_id,
                retrieved_context,
                user_settings,
                tool_hint,
            ) = await asyncio.gather(
                _get_budget(),
                conversation_manager.get_or_create(conversation_id, user_id=user_id),
                context_builder.build(query, user_id=user_id),
                _get_settings(),
                get_tool_hint(query),
            )

            # Background learning jobs — all throttled internally, never block.
            asyncio.create_task(skill_registry.update_skills())
            asyncio.create_task(learn_tool_chains())
            asyncio.create_task(refresh_efficiency_cache())

            persona_prompt = await asyncio.to_thread(
                build_persona_prompt, user_settings
            )

            # All model selection goes through the router — single authority.
            # Early cancellation guard — honour stop() calls that arrived before
            # the run started, before we create any clients or background tasks.
            if task_id in self._cancelled_tasks:
                raise asyncio.CancelledError()

            agent_model = self.router.select_for_run(
                query,
                has_tools=bool(tool_schemas),
                budget_remaining=budget_remaining,
            )

            # Log model selection decision (fire-and-forget).
            asyncio.create_task(
                decision_tracker.log_decision(
                    task_id=task_id,
                    decision_point="model_selection",
                    chosen=agent_model,
                    reasoning=(
                        f"prompt_version={PROMPT_VERSION}; "
                        f"router: has_tools={bool(tool_schemas)}, "
                        f"budget_remaining={budget_remaining:.2f}"
                    ),
                    confidence=0.85,
                    options=list(self.router.FALLBACK_CHAIN),
                    user_id=user_id,
                )
            )

            # Accumulate tool names used during this run for reflection.
            tools_used: list[str] = []

            # Reuse one client across planning, main loop, and summary calls.
            run_client = _openrouter_client()

            # ── Guard: reject duplicate streams on same conversation ──
            if conversation_id in self._active_conversations:
                existing = self._active_conversations[conversation_id]
                yield ExecutionEvent(
                    type=EventType.ERROR,
                    error=f"A run is already active for this conversation (task_id={existing}). Stop it first or start a new conversation.",
                )
                return
            self._active_conversations[conversation_id] = task_id

            # ── Round 2: both need conversation_id, independent of each other ─
            history, token_count = await asyncio.gather(
                conversation_manager.load_messages(conversation_id),
                conversation_manager.estimate_tokens(conversation_id),
            )

            # Add estimate for the current query
            token_count += len(query) // 4
            context_percent = (token_count / settings.MAX_CONTEXT_TOKENS) * 100

            yield ExecutionEvent(
                type=EventType.CONTEXT,
                context_tokens_used=token_count,
                context_tokens_max=settings.MAX_CONTEXT_TOKENS,
                context_percent=round(context_percent, 1),
            )

            if context_percent >= settings.CONTEXT_TRIGGER_PERCENT * 100:
                yield ExecutionEvent(
                    type=EventType.STATUS,
                    content=f"context at {context_percent:.0f}% — compacting conversation...",
                )
                summary = await self._summarize_history(
                    history, agent_model, run_client
                )
                await conversation_manager.compact(
                    conversation_id,
                    summary=summary,
                    keep_recent=settings.KEEP_RECENT_TURNS,
                )
                # Reload the now-compacted history
                history = await conversation_manager.load_messages(conversation_id)

            if retrieved_context:
                yield ExecutionEvent(
                    type=EventType.STATUS, content="searching memory and documents..."
                )

            # Build initial system prompt with optional persona and retrieved context.
            # Append tool hint after extra_context so it reads as a soft suggestion,
            # not a hard constraint.
            combined_context = context or ""
            if tool_hint:
                combined_context = (combined_context + "\n\n" + tool_hint).strip()
            system_base = build_system_prompt(
                retrieved_context,
                combined_context or None,
                persona_prompt,
                budget_remaining=budget_remaining,
                monthly_budget_usd=float(settings.OPENROUTER_BUDGET_MONTHLY),
            )

            # ── Plan-then-execute for qualifying multi-step queries ───
            plan_prefix = ""
            if await self.router.should_plan_async(
                query, has_tools=bool(tool_schemas), has_history=bool(history)
            ):
                yield ExecutionEvent(type=EventType.STATUS, content="planning...")
                plan_result = await self._make_plan(
                    query, context, agent_model, run_client
                )
                plan_prefix = plan_result.plan_markdown
                if plan_prefix:
                    yield ExecutionEvent(
                        type=EventType.THINKING, content=f"Plan:\n{plan_prefix}"
                    )
                    done_line = _extract_done_when_line(plan_prefix)
                    if done_line:
                        state.done_when = done_line
                        system_base += (
                            f"\n\n<success_criteria>\n{done_line}\n"
                            "Stop using tools and write your final response as soon as "
                            "this condition is met.\n</success_criteria>"
                        )
                    meta_lines = [
                        f"plan_confidence: {plan_result.plan_confidence:.0%}",
                    ]
                    if plan_result.fallback_if_wrong:
                        meta_lines.append(
                            f"fallback_if_wrong: {plan_result.fallback_if_wrong}"
                        )
                    if plan_result.risk_notes:
                        meta_lines.append(f"risk_notes: {plan_result.risk_notes}")
                    system_base += (
                        "\n\n<plan_meta>\n" + "\n".join(meta_lines) + "\n</plan_meta>"
                    )

                    asyncio.create_task(
                        decision_tracker.log_decision(
                            task_id=task_id,
                            decision_point="planning",
                            chosen="accepted_plan",
                            reasoning=(
                                plan_result.risk_notes
                                or plan_result.plan_markdown[:1000]
                            ),
                            confidence=plan_result.plan_confidence,
                            user_id=user_id,
                        )
                    )

            # System + history + new user message (with plan prepended if available)
            messages = [
                {
                    "role": "system",
                    "content": _compose_system_with_progress(system_base, state),
                }
            ]
            messages.extend(history)
            user_text = (
                f"[Plan]\n{plan_prefix}\n\n[Task]\n{query}" if plan_prefix else query
            )
            if images:
                user_content: Any = [{"type": "text", "text": user_text}]
                for img_url in images[:4]:
                    user_content.append(
                        {"type": "image_url", "image_url": {"url": img_url}}
                    )
            else:
                user_content = user_text
            messages.append({"role": "user", "content": user_content})

            if history:
                yield ExecutionEvent(
                    type=EventType.STATUS,
                    content=f"resuming conversation ({len(history) // 2} prior turns)...",
                )

            yield ExecutionEvent(type=EventType.STATUS, content="thinking...")

            for iteration in range(max_iterations):
                # Check for stop request before each LLM call
                if task_id in self._cancelled_tasks:
                    raise asyncio.CancelledError()
                if self._is_circuit_open():
                    raise RuntimeError(
                        "Circuit breaker open: retry after recovery window"
                    )

                state.current_step = iteration + 1
                state.last_update = datetime.utcnow()

                # ── Ask the LLM with classifier-based error recovery ──────────
                # Use the run-level client on the first call; error/timeout paths
                # below create fresh clients intentionally to reset connections.
                client = run_client
                current_model = agent_model
                response = None
                native_stream = None
                retry_counts: dict[str, int] = {}  # reason → attempts used

                while current_model:
                    try:
                        sampling = self.router.sampling_params_for_model(current_model)
                        create_kwargs: dict[str, Any] = {
                            "model": current_model,
                            "messages": messages,
                            "stream": True,
                            "stream_options": {"include_usage": True},
                            "temperature": sampling["temperature"],
                            "top_p": sampling["top_p"],
                        }
                        if tool_schemas:
                            create_kwargs["tools"] = tool_schemas
                            create_kwargs["tool_choice"] = "auto"
                        reasoning_extra = _openrouter_reasoning_extra_body(
                            reasoning_effort
                        )
                        if reasoning_extra:
                            create_kwargs["extra_body"] = reasoning_extra
                        llm_task = asyncio.create_task(
                            client.chat.completions.create(**create_kwargs),
                        )
                        wait_seconds = 0
                        while True:
                            try:
                                response = await asyncio.wait_for(
                                    asyncio.shield(llm_task), timeout=1.0
                                )
                                break
                            except asyncio.TimeoutError:
                                if task_id in self._cancelled_tasks:
                                    llm_task.cancel()
                                    try:
                                        await llm_task
                                    except asyncio.CancelledError:
                                        pass
                                    raise asyncio.CancelledError()
                                wait_seconds += 1
                                if wait_seconds % 2 == 0:
                                    yield ExecutionEvent(
                                        type=EventType.STATUS,
                                        content=f"thinking... ({wait_seconds}s)",
                                    )

                        if hasattr(response, "__aiter__"):
                            native_stream = response
                            response = None

                        if current_model != agent_model:
                            yield ExecutionEvent(
                                type=EventType.STATUS,
                                content=f"using fallback model: {current_model}",
                            )
                        self._record_circuit_success()
                        break

                    except asyncio.CancelledError:
                        raise

                    except Exception as e:
                        self._record_circuit_failure()
                        err = classify(e)
                        reason_key = err.reason.value

                        # Log error pattern (fire-and-forget).
                        if _db.db_pool:
                            recovery = (
                                "abort"
                                if err.is_fatal
                                else (
                                    "compress"
                                    if err.should_compress
                                    else (
                                        "rotate_model"
                                        if err.should_rotate_model
                                        else "retry"
                                    )
                                )
                            )
                            asyncio.create_task(
                                _db.execute(
                                    """
                                INSERT INTO error_patterns
                                    (error_type, task_id, model_used, query_snippet, recovery_strategy)
                                VALUES ($1, $2, $3, $4, $5)
                                """,
                                    err.reason.value,
                                    task_id,
                                    current_model,
                                    query[:200],
                                    recovery,
                                )
                            )

                        if err.is_fatal:
                            # Auth / billing / bad request — surface immediately
                            raise RuntimeError(
                                f"{err.reason.value}: {err.message}"
                            ) from e

                        if err.should_compress:
                            # Context too large — compact and retry this iteration
                            yield ExecutionEvent(
                                type=EventType.STATUS,
                                content="context too large — compacting...",
                            )
                            summary = await self._summarize_history(
                                await conversation_manager.load_messages(
                                    conversation_id
                                ),
                                current_model,
                            )
                            await conversation_manager.compact(
                                conversation_id, summary=summary
                            )
                            history = await conversation_manager.load_messages(
                                conversation_id
                            )
                            # Rebuild messages with compacted history
                            messages = [
                                {
                                    "role": "system",
                                    "content": _compose_system_with_progress(
                                        system_base, state
                                    ),
                                }
                            ]
                            messages.extend(history)
                            messages.append({"role": "user", "content": user_content})
                            client = _openrouter_client()
                            continue

                        if err.should_rotate_model:
                            # Model not found or tool use unsupported — rotate
                            next_model = self.router.get_next_fallback(current_model)
                            if next_model and next_model != current_model:
                                logger.warning(
                                    f"Model {current_model} failed ({err.reason.value}) — rotating to {next_model}"
                                )
                                yield ExecutionEvent(
                                    type=EventType.STATUS,
                                    content=f"model unavailable — trying {next_model.split('/')[-1]}...",
                                )
                                current_model = next_model
                                continue
                            raise RuntimeError(
                                f"All models in fallback chain failed: {err.message}"
                            ) from e

                        if err.is_retriable:
                            used = retry_counts.get(reason_key, 0)
                            if used < len(err.retry_delays):
                                delay = err.retry_delays[used]
                                retry_counts[reason_key] = used + 1
                                logger.warning(
                                    f"{err.reason.value} error (attempt {used + 1}) — retrying in {delay:.0f}s"
                                )
                                yield ExecutionEvent(
                                    type=EventType.STATUS,
                                    content=f"{err.reason.value.replace('_', ' ')} — retrying in {delay:.0f}s...",
                                )
                                if delay > 0:
                                    await asyncio.sleep(delay)
                                if err.reason == FailoverReason.timeout:
                                    client = (
                                        _openrouter_client()
                                    )  # fresh client on timeout
                                continue
                            # Exhausted retries — rotate model as last resort
                            next_model = self.router.get_next_fallback(current_model)
                            if next_model and next_model != current_model:
                                logger.warning(
                                    f"Retries exhausted for {current_model} — rotating to {next_model}"
                                )
                                current_model = next_model
                                retry_counts = {}
                                continue

                        raise

                if native_stream is None and response is None:
                    raise RuntimeError("All models in fallback chain failed")

                agent_model = current_model  # update in case fallback was used
                msg_content = ""
                msg_tool_calls: list[dict] = []
                prompt_tokens = 0
                completion_tokens = 0

                # ── Native provider streaming path (content + tool-call deltas) ──────
                if native_stream is not None:
                    yield ExecutionEvent(type=EventType.STATUS, content="responding...")

                    final_parts: list[str] = []
                    streamed_tool_calls: dict[int, dict[str, str]] = {}

                    async for chunk in native_stream:
                        # Usage may be present on the final chunk when include_usage=True.
                        usage = getattr(chunk, "usage", None)
                        if usage is not None:
                            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                            completion_tokens = int(
                                getattr(usage, "completion_tokens", 0) or 0
                            )

                        choices = getattr(chunk, "choices", None) or []
                        if not choices:
                            continue
                        delta = getattr(choices[0], "delta", None)
                        if delta is None:
                            continue

                        piece = getattr(delta, "content", None)
                        emitted_list_reasoning = False
                        if piece:
                            if isinstance(piece, list):
                                text_parts: list[str] = []
                                for p in piece:
                                    if not isinstance(p, dict):
                                        continue
                                    p_type = str(p.get("type") or "").lower()
                                    if p_type in ("thinking", "reasoning"):
                                        inner = p.get("thinking") or p.get("text")
                                        if isinstance(inner, str) and inner:
                                            emitted_list_reasoning = True
                                            yield ExecutionEvent(
                                                type=EventType.REASONING_DELTA,
                                                content=inner,
                                                model=agent_model,
                                            )
                                    elif p_type == "text":
                                        t = p.get("text")
                                        if isinstance(t, str):
                                            text_parts.append(t)
                                text_piece = "".join(text_parts)
                            else:
                                text_piece = str(piece)

                            if text_piece:
                                final_parts.append(text_piece)
                                yield ExecutionEvent(
                                    type=EventType.TEXT_DELTA,
                                    content=text_piece,
                                    model=agent_model,
                                )

                        if not emitted_list_reasoning:
                            reasoning_piece = _reasoning_delta_snippet(delta)
                            if reasoning_piece:
                                yield ExecutionEvent(
                                    type=EventType.REASONING_DELTA,
                                    content=reasoning_piece,
                                    model=agent_model,
                                )

                        for tc in getattr(delta, "tool_calls", None) or []:
                            idx = int(getattr(tc, "index", 0) or 0)
                            slot = streamed_tool_calls.setdefault(
                                idx,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            tc_id = getattr(tc, "id", None)
                            if tc_id:
                                slot["id"] = tc_id
                            fn = getattr(tc, "function", None)
                            if fn is not None:
                                fn_name = getattr(fn, "name", None)
                                if fn_name:
                                    slot["name"] += fn_name
                                fn_args = getattr(fn, "arguments", None)
                                if fn_args:
                                    slot["arguments"] += fn_args

                    msg_content = "".join(final_parts)
                    for idx in sorted(streamed_tool_calls.keys()):
                        tc = streamed_tool_calls[idx]
                        if not tc["name"] and not tc["arguments"]:
                            continue
                        msg_tool_calls.append(
                            {
                                "id": tc["id"] or f"call-{uuid.uuid4()}",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                        )

                else:
                    msg = response.choices[0].message
                    msg_content = msg.content or ""
                    for tc in msg.tool_calls or []:
                        msg_tool_calls.append(
                            {
                                "id": tc.id,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                        )
                    if response.usage:
                        prompt_tokens = int(
                            getattr(response.usage, "prompt_tokens", 0) or 0
                        )
                        completion_tokens = int(
                            getattr(response.usage, "completion_tokens", 0) or 0
                        )

                # ── Track cost for every LLM call (tool-use and final) ───────
                if (prompt_tokens or completion_tokens) and self.cost_tracker:
                    try:
                        await self.cost_tracker.track_cost(
                            model=agent_model,
                            input_tokens=prompt_tokens,
                            output_tokens=completion_tokens,
                            task_id=task_id,
                        )
                    except Exception as e:
                        logger.warning(f"Cost tracking failed: {e}")

                # ── No tool calls → stream final answer ──────────────────────
                if not msg_tool_calls:
                    final_text = msg_content

                    # Non-stream fallback path: still emit incremental chunks for UX.
                    if native_stream is None:
                        yield ExecutionEvent(
                            type=EventType.STATUS, content="responding..."
                        )
                        chunk_size = 12
                        for i in range(0, len(final_text), chunk_size):
                            yield ExecutionEvent(
                                type=EventType.TEXT_DELTA,
                                content=final_text[i : i + chunk_size],
                                model=agent_model,
                            )
                            await asyncio.sleep(0.12)

                    # ── Save turn to conversation history ─────────────
                    try:
                        await conversation_manager.save_turn(
                            conversation_id=conversation_id,
                            user_message=query,
                            assistant_message=final_text,
                            user_tokens=prompt_tokens,
                            assistant_tokens=completion_tokens,
                        )
                    except Exception as e:
                        logger.warning(f"Conversation save failed: {e}")

                    # ── Auto-save insight to long-term memory ──────────
                    # Skip trivial turns and low-value follow-up edits in
                    # existing conversations to reduce token spend.
                    if self.router.should_remember(
                        query,
                        has_history=bool(history),
                        response=final_text,
                    ):
                        try:
                            await memory_manager.save_interaction(
                                query=query,
                                response=final_text,
                                user_id=user_id,
                            )
                        except Exception as e:
                            logger.warning(f"Memory save failed: {e}")
                    else:
                        logger.debug("Skipping memory extraction for low-value turn")

                    # Post-task reflection + outcome marking (fire-and-forget).
                    asyncio.create_task(
                        post_task_reflection(
                            task_id=task_id,
                            query=query,
                            result=final_text,
                            success=True,
                            model_used=agent_model,
                            tools_used=list(tools_used),
                            user_id=user_id,
                        )
                    )
                    asyncio.create_task(
                        decision_tracker.mark_outcome(task_id, "success")
                    )

                    break  # Done

                # ── Tool calls → execute each one ─────────────────────────────
                # Add the assistant's tool-calling message to history
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg_content,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": tc["function"]["arguments"],
                                },
                            }
                            for tc in msg_tool_calls
                        ],
                    }
                )

                # Parse all tool calls first
                parsed_calls = []
                for tool_call in msg_tool_calls:
                    name = tool_call["function"]["name"]
                    try:
                        args = json.loads(tool_call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    parsed_calls.append((tool_call["id"], name, args))
                    state.working_memory.append(
                        {
                            "iteration": iteration + 1,
                            "type": "planned_tool_call",
                            "tool": name,
                            "args": args,
                        }
                    )
                    yield ExecutionEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=name,
                        tool_input=args,
                    )

                # Execute all tools in parallel, logging each call
                async def _run_tool(call_id: str, name: str, args: dict):
                    from app.database import execute as db_execute
                    import time as _time

                    t0 = _time.monotonic()
                    err_str = None
                    truncated = False
                    result_str = ""
                    tools_used.append(name)
                    asyncio.create_task(
                        decision_tracker.log_decision(
                            task_id=task_id,
                            decision_point="tool_selection",
                            chosen=name,
                            reasoning="agent selected via ReAct loop",
                            confidence=0.75,
                            user_id=user_id,
                        )
                    )
                    try:
                        result = await self.tools.call(name, **args)
                        if isinstance(result, (dict, list)):
                            result_str = json.dumps(result, default=str)
                        else:
                            result_str = str(result)
                        truncated_str = truncate_tail(result_str)
                        if truncated_str != result_str:
                            logger.warning(
                                f"Tool '{name}' result truncated ({len(result_str)} chars → tail kept)"
                            )
                            result_str = truncated_str
                            truncated = True
                    except Exception as e:
                        err_str = str(e)
                        result_str = f"Tool error: {e}"
                    finally:
                        duration_ms = int((_time.monotonic() - t0) * 1000)
                        if _db.db_pool:
                            try:
                                await db_execute(
                                    """
                                    INSERT INTO tool_calls
                                        (task_id, conversation_id, iteration, tool_name,
                                         input_json, output_text, error, duration_ms, truncated)
                                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                                    """,
                                    task_id,
                                    conversation_id,
                                    iteration + 1,
                                    name,
                                    json.dumps(args),
                                    result_str[:2000],
                                    err_str,
                                    duration_ms,
                                    truncated,
                                )
                            except Exception as log_err:
                                logger.debug(f"Tool call logging failed: {log_err}")
                    return call_id, name, result_str, err_str

                tool_results = await asyncio.gather(
                    *[_run_tool(cid, n, a) for cid, n, a in parsed_calls]
                )

                for call_id, name, result_str, err in tool_results:
                    if err:
                        state.working_memory.append(
                            {
                                "iteration": iteration + 1,
                                "type": "tool_error",
                                "tool": name,
                                "error": err,
                            }
                        )
                        yield ExecutionEvent(
                            type=EventType.ERROR, error=f"{name} failed: {err}"
                        )
                    else:
                        state.working_memory.append(
                            {
                                "iteration": iteration + 1,
                                "type": "tool_result",
                                "tool": name,
                                "result_preview": result_str[:300],
                            }
                        )
                        yield ExecutionEvent(
                            type=EventType.TOOL_RESULT,
                            tool_name=name,
                            tool_result=result_str,
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": result_str,
                        }
                    )

                messages[0]["content"] = _compose_system_with_progress(
                    system_base, state
                )

                yield ExecutionEvent(
                    type=EventType.STATUS,
                    content=f"processing results (round {iteration + 1})...",
                )

            else:
                # Hit max_iterations without a final answer
                yield ExecutionEvent(
                    type=EventType.STATUS,
                    content="max iterations reached, summarising...",
                )
                yield ExecutionEvent(
                    type=EventType.TEXT_DELTA,
                    content="I reached the maximum number of steps. Here's what I found so far based on the tool results above.",
                    model=agent_model,
                )

            state.status = TaskStatus.COMPLETED
            yield ExecutionEvent(
                type=EventType.DONE,
                content="complete",
                conversation_id=conversation_id,
            )

        except asyncio.CancelledError:
            state.status = TaskStatus.STOPPED
            yield ExecutionEvent(type=EventType.STATUS, content="stopped by user")

        except Exception as e:
            state.status = TaskStatus.FAILED
            state.errors.append(str(e))
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            asyncio.create_task(decision_tracker.mark_outcome(task_id, "failure"))
            yield ExecutionEvent(type=EventType.ERROR, error=f"Execution failed: {e}")

        finally:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            self._cancelled_tasks.discard(task_id)
            # Release conversation lock so a new run can start
            if (
                conversation_id
                and self._active_conversations.get(conversation_id) == task_id
            ):
                del self._active_conversations[conversation_id]

    async def _make_plan(
        self,
        query: str,
        context: Optional[str],
        model: str,
        client: Optional[AsyncOpenAI] = None,
    ) -> PlanResult:
        """
        Ask the cheap model for a JSON plan: markdown steps + confidence + fallback hints.
        Parses with _parse_plan_llm_output (tolerates prose-only replies).
        """
        plan_prompt = (
            "You are a planning assistant. Reply with ONLY a single JSON object "
            "(no markdown fences, no commentary) using exactly these keys:\n"
            '- "plan_markdown": string — a short numbered plan (max 5 steps) plus a final line '
            'starting exactly with "Done when: " giving a verifiable completion condition.\n'
            '- "plan_confidence": number from 0 to 100 — how confident you are the plan will succeed.\n'
            '- "fallback_if_wrong": string — one line on what to try if the plan fails or key assumptions are wrong.\n'
            '- "risk_notes": string — brief unknowns or risks (omit or leave empty).\n\n'
            "Do not execute anything — only plan.\n\n"
            f"Task: {query}"
        )
        if context:
            plan_prompt += f"\nContext: {context}"

        try:
            c = client or _openrouter_client()
            resp = await c.chat.completions.create(
                model=settings.DEFAULT_MODEL_SIMPLE,
                messages=[{"role": "user", "content": plan_prompt}],
                max_tokens=420,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _parse_plan_llm_output(raw)
        except Exception as e:
            logger.warning(f"Planning step failed: {e}")
            return PlanResult("", 0.45, "", "")

    async def _summarize_history(
        self, history: list[dict], model: str, client: Optional[AsyncOpenAI] = None
    ) -> str:
        """
        Summarize conversation history into a structured compact form.

        - Prunes long tool outputs before sending to the summarizer
        - Preserves prior compaction summaries across multiple cycles
        - Tracks files referenced in tool calls (read vs modified)
        - Uses a structured Goal/Progress/Key Decisions/Next Steps template
        - Scales max_tokens proportionally to content size (clamped 400–1500)
        """
        import re as _re

        if not history:
            return ""

        _TOOL_PLACEHOLDER = "[tool output truncated]"
        _MAX_TOOL_CHARS = 800  # raised from 300 — summarizer needs raw detail to produce accurate context
        _MAX_MSG_CHARS = 800
        _KEEP_RECENT_FULL = (
            2  # preserve last N assistant+tool pairs in full (freshest signal)
        )

        # ── Separate prior compaction summary ────────────────────────────────
        prior_summary = ""
        turns = []
        for m in history:
            content = m.get("content") or ""
            if content.startswith("[CONTEXT COMPACTION"):
                normalized_content = content.replace("\r\n", "\n")
                if "\n\n" in normalized_content:
                    body = normalized_content.split("\n\n", 1)[1].strip()
                else:
                    body = normalized_content.split("\n", 1)[-1].strip()
                prior_summary = body
            else:
                turns.append(m)

        # ── Extract file operations from tool call data ───────────────────────
        # tool_calls in assistant messages carry {"function": {"name": ..., "arguments": ...}}
        read_files: set[str] = set()
        modified_files: set[str] = set()
        _FILE_OP_TOOL = "file_operations"
        _PATH_RE = _re.compile(r'"path"\s*:\s*"([^"]+)"')

        for m in turns:
            tool_calls = m.get("tool_calls") or []
            for tc in tool_calls:
                try:
                    fn = tc.get("function", {})
                    if fn.get("name") != _FILE_OP_TOOL:
                        continue
                    args_str = fn.get("arguments", "{}")
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                    path = args.get("path", "")
                    op = args.get("operation", "")
                    if not path:
                        continue
                    if op == "read":
                        read_files.add(path)
                    elif op in ("write", "delete"):
                        modified_files.add(path)
                        read_files.discard(path)
                except Exception:
                    pass
            # Also scan content for path patterns (fallback for stored messages)
            content = m.get("content") or ""
            for match in _PATH_RE.finditer(content):
                read_files.add(match.group(1))

        # ── Prune tool outputs ────────────────────────────────────────────────
        # Most recent turns are preserved in full — they carry the freshest signal
        # and are most critical for the agent to continue accurately after compaction.
        # Older turns are truncated to limit summarizer input size.
        cutoff = max(
            0, len(turns) - (_KEEP_RECENT_FULL * 2)
        )  # *2 for assistant+tool pairs
        pruned = []
        for i, m in enumerate(turns):
            role = m.get("role", "")
            content = m.get("content") or ""
            if i >= cutoff:
                # Recent turn — keep in full
                pruned.append({"role": role, "content": content})
                continue
            if role == "tool" and len(content) > _MAX_TOOL_CHARS:
                content = content[:_MAX_TOOL_CHARS] + f" {_TOOL_PLACEHOLDER}"
            elif len(content) > _MAX_MSG_CHARS:
                content = content[:_MAX_MSG_CHARS] + "…"
            pruned.append({"role": role, "content": content})

        # ── Format conversation for summarizer ────────────────────────────────
        conv_lines = []
        if prior_summary:
            conv_lines.append(f"[Prior summary]\n{prior_summary}\n")
        for m in pruned:
            conv_lines.append(f"[{m['role'].capitalize()}]: {m['content']}")
        formatted = "\n".join(conv_lines)

        # ── Build file tracking appendix ──────────────────────────────────────
        file_section = ""
        read_only = sorted(read_files - modified_files)
        modified = sorted(modified_files)
        if read_only:
            file_section += (
                "\n<read-files>\n" + "\n".join(read_only) + "\n</read-files>"
            )
        if modified:
            file_section += (
                "\n<modified-files>\n" + "\n".join(modified) + "\n</modified-files>"
            )

        # ── Scale token budget ────────────────────────────────────────────────
        raw_chars = sum(len(m.get("content") or "") for m in history)
        budget = max(400, min(1500, int(raw_chars / 4 * 0.20)))

        prompt = (
            "Summarize this conversation to free up context space. "
            "Use exactly this structure (omit sections with nothing to say):\n\n"
            "## Goal\n"
            "[What the user is trying to accomplish]\n\n"
            "## Progress\n"
            "### Done\n"
            "- [x] [Completed tasks with specific outcomes]\n\n"
            "### In Progress\n"
            "- [ ] [Current work]\n\n"
            "### Blocked\n"
            "- [Issues, if any]\n\n"
            "## Key Decisions\n"
            "- **[Decision]**: [Rationale]\n\n"
            "## Next Steps\n"
            "1. [What should happen next]\n\n"
            "## Critical Context\n"
            "- [Specific values, file names, API responses, or data needed to continue]\n\n"
            "Rules:\n"
            "- Be specific — include concrete values, paths, and decisions.\n"
            "- Do NOT reproduce instructions or requests — only facts and outcomes.\n\n"
            "Conversation:\n"
            f"{formatted}"
        )

        try:
            c = client or _openrouter_client()
            resp = await c.chat.completions.create(
                model=settings.DEFAULT_MODEL_SIMPLE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=budget,
                temperature=0,
            )
            summary = (resp.choices[0].message.content or "").strip()
            return summary + file_section if file_section else summary
        except Exception as e:
            logger.warning(f"History summarization failed: {e}")
            return prior_summary or "Previous conversation context was compacted."

    async def stop_task(self, task_id: str) -> bool:
        if task_id in self.active_tasks:
            self.active_tasks[task_id].status = TaskStatus.STOPPED
            self._cancelled_tasks.add(task_id)
            return True
        return False

    def get_available_tools(self) -> list[str]:
        return self.tools.list_tools()

    async def run_sub_agent(
        self,
        *,
        query: str,
        user_id: Optional[str] = None,
        max_iterations: int = 6,
        depth: int = 1,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """
        Agent-as-tool pattern: run a constrained nested agent task.
        """
        if depth > max_depth:
            raise ValueError("sub-agent max depth exceeded")
        result, conversation_id = await self.run(
            query=query,
            user_id=user_id,
            max_iterations=max_iterations,
        )
        return {
            "depth": depth,
            "conversation_id": conversation_id,
            "result": result,
        }
