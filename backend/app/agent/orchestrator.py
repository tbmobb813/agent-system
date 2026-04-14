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
import uuid
import logging
from datetime import datetime
from typing import AsyncIterator, Optional
from pydantic import BaseModel
from openai import AsyncOpenAI

from app.config import settings
from app.models import ExecutionEvent, EventType, TaskStatus
from app.agent.router import ModelRouter
from app.agent.memory import memory_manager
from app.agent.conversation import conversation_manager
from app.agent.documents import get_context_for_query as doc_context_for_query
from app.tools.tool_registry import ToolRegistry


def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "http://localhost:3003",
            "X-Title": "Personal AI Agent",
        },
    )


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a capable personal AI assistant with access to tools.

Guidelines:
- Use tools when you need current information, need to interact with external systems, or when computation would help.
- You can call multiple tools across multiple rounds — each tool result is fed back to you.
- When you have enough information, respond directly without calling any more tools.
- Be concise and direct. Don't explain what you're about to do — just do it.
- If a tool fails, try a different approach or answer from your own knowledge."""


class ExecutionState(BaseModel):
    task_id: str
    status: TaskStatus
    current_step: int
    total_steps: int
    results: dict = {}
    errors: list = []
    start_time: datetime
    last_update: datetime


class AgentOrchestrator:
    def __init__(self, cost_tracker=None):
        self.cost_tracker = cost_tracker
        self.router = ModelRouter()
        self.tools = ToolRegistry()
        self.active_tasks = {}

    async def run(
        self,
        query: str,
        context: Optional[str] = None,
        tools: Optional[list[str]] = None,
        user_id: Optional[str] = None,
        max_iterations: int = 10,
        conversation_id: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Execute agent synchronously. Returns (result, conversation_id)."""
        task_id = str(uuid.uuid4())
        result = ""
        final_conversation_id = conversation_id
        async for event in self.stream(
            query=query, context=context, tools=tools,
            user_id=user_id, max_iterations=max_iterations,
            task_id=task_id, conversation_id=conversation_id,
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
            start_time=datetime.utcnow(),
            last_update=datetime.utcnow(),
        )
        self.active_tasks[task_id] = state

        try:
            tool_schemas = self.tools.get_tool_schemas(tools)

            # Get remaining budget for cost-aware routing
            budget_remaining = settings.OPENROUTER_BUDGET_MONTHLY
            if self.cost_tracker:
                try:
                    spent = await self.cost_tracker.get_spent_today()
                    budget_remaining = settings.OPENROUTER_BUDGET_MONTHLY - spent
                except Exception:
                    pass

            # Tool use always routes to agent tier (reliable function calling).
            # No-tool queries use budget-aware complexity routing.
            agent_model = (
                self.router.MODELS["agent"]["model"]
                if tool_schemas
                else self.router.select_model(query, budget_remaining=budget_remaining)
            )

            # ── Get/create conversation ───────────────────────────────
            conversation_id = await conversation_manager.get_or_create(
                conversation_id, user_id=user_id
            )

            # ── Load conversation history ─────────────────────────────
            history = await conversation_manager.load_messages(conversation_id)

            # ── Context usage check + auto-compaction ─────────────────
            token_count = await conversation_manager.estimate_tokens(conversation_id)
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
                summary = await self._summarize_history(history, agent_model)
                await conversation_manager.compact(
                    conversation_id,
                    summary=summary,
                    keep_recent=settings.KEEP_RECENT_TURNS,
                )
                # Reload the now-compacted history
                history = await conversation_manager.load_messages(conversation_id)

            # ── Fetch relevant memories + document chunks in parallel ─
            memory_context, doc_context = await asyncio.gather(
                memory_manager.get_context_for_query(query, user_id=user_id),
                doc_context_for_query(query, user_id=user_id),
            )

            if doc_context:
                yield ExecutionEvent(type=EventType.STATUS, content="searching your documents...")

            # Build initial message list
            system = SYSTEM_PROMPT
            if memory_context:
                system += f"\n\n{memory_context}"
            if doc_context:
                system += f"\n\n{doc_context}"
            if context:
                system += f"\n\nAdditional context: {context}"

            # System + history + new user message (with plan prepended if available)
            messages = [{"role": "system", "content": system}]
            messages.extend(history)
            user_content = f"[Plan]\n{plan_prefix}\n\n[Task]\n{query}" if plan_prefix else query
            messages.append({"role": "user", "content": user_content})

            if history:
                yield ExecutionEvent(type=EventType.STATUS, content=f"resuming conversation ({len(history) // 2} prior turns)...")
            if memory_context:
                yield ExecutionEvent(type=EventType.STATUS, content="recalling relevant memories...")

            # ── Plan-then-execute for complex multi-step queries ──────
            plan_prefix = ""
            if tool_schemas and self.router.is_complex(query):
                yield ExecutionEvent(type=EventType.STATUS, content="planning...")
                plan_prefix = await self._make_plan(query, context, agent_model)
                if plan_prefix:
                    yield ExecutionEvent(type=EventType.THINKING, content=f"Plan:\n{plan_prefix}")

            yield ExecutionEvent(type=EventType.STATUS, content="thinking...")

            for iteration in range(max_iterations):
                state.current_step = iteration + 1
                state.last_update = datetime.utcnow()

                # ── Ask the LLM with fallback on model errors ─────────────────
                client = _openrouter_client()
                current_model = agent_model
                response = None
                while current_model:
                    try:
                        response = await client.chat.completions.create(
                            model=current_model,
                            messages=messages,
                            tools=tool_schemas if tool_schemas else None,
                            tool_choice="auto" if tool_schemas else None,
                        )
                        if current_model != agent_model:
                            yield ExecutionEvent(type=EventType.STATUS, content=f"using fallback model: {current_model}")
                        break
                    except Exception as e:
                        err_str = str(e)
                        # Only fall back on model-related errors (404, invalid model, tool use unsupported)
                        if any(code in err_str for code in ["404", "400", "tool", "model"]):
                            next_model = self.router.get_next_fallback(current_model)
                            if next_model and next_model != current_model:
                                logger.warning(f"Model {current_model} failed ({e}) — trying {next_model}")
                                current_model = next_model
                            else:
                                raise
                        else:
                            raise
                if response is None:
                    raise RuntimeError("All models in fallback chain failed")

                agent_model = current_model  # update in case fallback was used
                msg = response.choices[0].message

                # ── No tool calls → stream final answer ──────────────────────
                if not msg.tool_calls:
                    final_text = msg.content or ""

                    # Track cost from this non-streaming call
                    if response.usage and self.cost_tracker:
                        try:
                            await self.cost_tracker.track_cost(
                                model=agent_model,
                                input_tokens=response.usage.prompt_tokens,
                                output_tokens=response.usage.completion_tokens,
                                task_id=task_id,
                            )
                        except Exception as e:
                            logger.warning(f"Cost tracking failed: {e}")

                    yield ExecutionEvent(type=EventType.STATUS, content="responding...")

                    # Stream text in chunks for a live feel
                    chunk_size = 40
                    for i in range(0, len(final_text), chunk_size):
                        yield ExecutionEvent(
                            type=EventType.TEXT_DELTA,
                            content=final_text[i:i + chunk_size],
                            model=agent_model,
                        )

                    # ── Save turn to conversation history ─────────────
                    try:
                        await conversation_manager.save_turn(
                            conversation_id=conversation_id,
                            user_message=query,
                            assistant_message=final_text,
                            user_tokens=response.usage.prompt_tokens if response.usage else 0,
                            assistant_tokens=response.usage.completion_tokens if response.usage else 0,
                        )
                    except Exception as e:
                        logger.warning(f"Conversation save failed: {e}")

                    # ── Auto-save insight to long-term memory ──────────
                    try:
                        await memory_manager.save_interaction(
                            query=query,
                            response=final_text,
                            user_id=user_id,
                        )
                    except Exception as e:
                        logger.warning(f"Memory save failed: {e}")

                    break  # Done

                # ── Tool calls → execute each one ─────────────────────────────
                # Add the assistant's tool-calling message to history
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })

                # Parse all tool calls first
                parsed_calls = []
                for tool_call in msg.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    parsed_calls.append((tool_call.id, name, args))
                    yield ExecutionEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=name,
                        tool_input=args,
                    )

                # Execute all tools in parallel
                async def _run_tool(call_id: str, name: str, args: dict):
                    try:
                        result = await self.tools.call(name, **args)
                        return call_id, name, str(result)[:4000], None
                    except Exception as e:
                        return call_id, name, f"Tool error: {e}", str(e)

                tool_results = await asyncio.gather(
                    *[_run_tool(cid, n, a) for cid, n, a in parsed_calls]
                )

                for call_id, name, result_str, err in tool_results:
                    if err:
                        yield ExecutionEvent(type=EventType.ERROR, error=f"{name} failed: {err}")
                    else:
                        yield ExecutionEvent(
                            type=EventType.TOOL_RESULT,
                            tool_name=name,
                            tool_result=result_str,
                        )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_str,
                    })

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
            yield ExecutionEvent(type=EventType.ERROR, error=f"Execution failed: {e}")

        finally:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

    async def _make_plan(self, query: str, context: Optional[str], model: str) -> str:
        """
        Ask the model to produce a concise numbered plan before executing.
        Uses the cheap model to keep cost low — plan is short and structured.
        """
        plan_prompt = (
            "You are a planning assistant. Given the following task, produce a short numbered "
            "step-by-step plan (max 5 steps) of what needs to be done to complete it. "
            "Be specific but concise. Do not execute anything — just plan.\n\n"
            f"Task: {query}"
        )
        if context:
            plan_prompt += f"\nContext: {context}"

        try:
            client = _openrouter_client()
            resp = await client.chat.completions.create(
                model=settings.DEFAULT_MODEL_SIMPLE,
                messages=[{"role": "user", "content": plan_prompt}],
                max_tokens=200,
                temperature=0,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Planning step failed: {e}")
            return ""

    async def _summarize_history(self, history: list[dict], model: str) -> str:
        """Summarize a list of past messages into a compact paragraph."""
        if not history:
            return ""
        formatted = "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}" for m in history
        )
        prompt = (
            "Summarize the following conversation history into a concise paragraph "
            "that preserves all key facts, decisions, and context needed to continue "
            "the conversation. Be brief but complete.\n\n"
            f"{formatted}"
        )
        try:
            client = _openrouter_client()
            resp = await client.chat.completions.create(
                model=settings.DEFAULT_MODEL_SIMPLE,   # use cheap model for summaries
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"History summarization failed: {e}")
            return "Previous conversation context was compacted."

    async def stop_task(self, task_id: str) -> bool:
        if task_id in self.active_tasks:
            self.active_tasks[task_id].status = TaskStatus.STOPPED
            return True
        return False

    def get_available_tools(self) -> list[str]:
        return self.tools.list_tools()
