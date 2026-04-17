"""
Agent routes — modular APIRouter for /agent/* endpoints.

To wire into main.py:
    from app.routes.agent import router as agent_router
    app.include_router(agent_router)

And store orchestrator/cost_tracker on app.state in lifespan:
    app.state.cost_tracker = CostTracker()
    app.state.agent_orchestrator = AgentOrchestrator(cost_tracker=app.state.cost_tracker)
"""

import asyncio
import uuid
import time
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import settings
from app.models import AgentRequest, AgentResponse, TaskStatus
from app.utils.auth import verify_api_key
from app.utils.limiter import limiter
from app.utils.streaming import format_sse_event
from app.database import execute
from app import database as _db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _orchestrator(request: Request):
    orch = getattr(request.app.state, "agent_orchestrator", None)
    if not orch:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return orch


def _cost_tracker(request: Request):
    ct = getattr(request.app.state, "cost_tracker", None)
    if not ct:
        raise HTTPException(status_code=503, detail="Cost tracker not initialized")
    return ct


@router.post("/run")
@limiter.limit("20/minute")
async def run_agent(
    request: Request,
    body: AgentRequest,
    api_key: str = Depends(verify_api_key),
):
    """Execute agent synchronously. Returns final result only."""
    orchestrator = _orchestrator(request)
    cost_tracker = _cost_tracker(request)

    estimated_cost = await cost_tracker.estimate_cost(body.query)
    remaining = settings.OPENROUTER_BUDGET_MONTHLY - await cost_tracker.get_spent_month()

    if estimated_cost > remaining:
        return JSONResponse(
            status_code=402,
            content={
                "error": "Insufficient budget",
                "spent_month": await cost_tracker.get_spent_month(),
                "budget": settings.OPENROUTER_BUDGET_MONTHLY,
                "estimated_cost": estimated_cost,
            },
        )

    t0 = time.monotonic()
    result, conv_id = await orchestrator.run(
        query=body.query,
        context=body.context,
        tools=body.tools,
        user_id=body.user_id,
        max_iterations=body.max_iterations,
        conversation_id=body.conversation_id,
    )
    elapsed = time.monotonic() - t0

    return AgentResponse(
        query=body.query,
        result=result,
        status="completed",
        cost=await cost_tracker.get_last_call_cost(task_id=None),
        model_used=cost_tracker.get_last_model(task_id=None),
        tokens=cost_tracker.get_last_usage(task_id=None),
        execution_time=round(elapsed, 3),
        conversation_id=conv_id,
    )


@router.post("/stream")
@limiter.limit("20/minute")
async def stream_agent(
    request: Request,
    body: AgentRequest,
    api_key: str = Depends(verify_api_key),
):
    """Execute agent with real-time SSE streaming."""
    orchestrator = _orchestrator(request)
    cost_tracker = _cost_tracker(request)

    task_id = str(uuid.uuid4())
    user_id = body.user_id
    started_at = datetime.utcnow()

    async def _persist_terminal_status(status: str):
        if not _db.db_pool:
            return
        try:
            await execute(
                "UPDATE tasks SET status = $1, completed_at = $2 WHERE id = $3",
                status, datetime.utcnow(), task_id,
            )
        except Exception as e:
            logger.warning(f"Could not update task status: {e}")

    async def generate():
        _stream = None
        try:
            estimated_cost = await cost_tracker.estimate_cost(body.query)
            remaining = settings.OPENROUTER_BUDGET_MONTHLY - await cost_tracker.get_spent_month()

            if estimated_cost > remaining:
                yield format_sse_event({
                    "type": "error",
                    "error": "Insufficient budget",
                    "spent": await cost_tracker.get_spent_month(),
                    "budget": settings.OPENROUTER_BUDGET_MONTHLY,
                })
                return

            yield format_sse_event({"type": "status", "content": "initializing", "task_id": task_id})

            # Pre-insert task as running
            if _db.db_pool:
                try:
                    await execute(
                        """
                        INSERT INTO tasks (id, user_id, query, status, cost, created_at)
                        VALUES ($1, $2, $3, 'running', 0, $4)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        task_id, user_id, body.query, started_at,
                    )
                except Exception as e:
                    logger.warning(f"Could not pre-insert task: {e}")

            result_parts = []
            status = "completed"
            model_used = None
            got_done = False
            stream_started_at = time.monotonic()

            _stream = orchestrator.stream(
                query=body.query,
                context=body.context,
                tools=body.tools,
                user_id=user_id,
                max_iterations=body.max_iterations,
                task_id=task_id,
                conversation_id=body.conversation_id,
            )
            while True:
                try:
                    remaining_timeout = settings.MAX_STREAM_SECONDS - (
                        time.monotonic() - stream_started_at
                    )
                    if remaining_timeout <= 0:
                        raise asyncio.TimeoutError()

                    event = await asyncio.wait_for(
                        _stream.__anext__(),
                        timeout=remaining_timeout,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    status = "failed"
                    await _persist_terminal_status(status)
                    if _stream is not None:
                        try:
                            await _stream.aclose()
                        except Exception as close_error:
                            logger.debug(f"Failed to close timed out stream: {close_error}")
                    yield format_sse_event({
                        "type": "error",
                        "error": f"Run timed out after {settings.MAX_STREAM_SECONDS}s",
                    })
                    return

                data = event.model_dump(mode="json")
                if event.type.value == "text_delta" and event.content:
                    result_parts.append(event.content)
                    if event.model and not model_used:
                        model_used = event.model
                if event.type.value == "error":
                    status = "failed"
                if event.type.value == "status" and event.content == "stopped by user":
                    status = "stopped"
                if event.type.value == "done":
                    got_done = True
                    final_cost = await cost_tracker.get_last_call_cost(task_id=task_id)
                    data["cost"] = final_cost
                    # Persist completed task
                    if _db.db_pool:
                        try:
                            elapsed = (datetime.utcnow() - started_at).total_seconds()
                            await execute(
                                """
                                UPDATE tasks
                                SET status = $1, result = $2, cost = $3,
                                    completed_at = $4, execution_time = $5,
                                    model_used = $6
                                WHERE id = $7
                                """,
                                status,
                                "".join(result_parts)[:10000],
                                final_cost,
                                datetime.utcnow(),
                                elapsed,
                                model_used,
                                task_id,
                            )
                        except Exception as e:
                            logger.warning(f"Could not update task record: {e}")
                yield format_sse_event(data)

            # Stream ended without DONE (stopped or interrupted) — update DB
            if not got_done:
                await _persist_terminal_status(status)

        except asyncio.CancelledError:
            if _stream is not None:
                try:
                    await _stream.aclose()
                except Exception as close_error:
                    logger.debug(f"Failed to close cancelled stream: {close_error}")
            raise
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield format_sse_event({"type": "error", "error": str(e)})
        finally:
            if await request.is_disconnected() and _stream is not None:
                try:
                    await _stream.aclose()
                except Exception as close_error:
                    logger.debug(f"Failed to close disconnected stream: {close_error}")
            pop_call_info = getattr(cost_tracker, "pop_call_info", None)
            if callable(pop_call_info):
                try:
                    pop_call_info(task_id)
                except Exception as pop_error:
                    logger.debug(f"Failed to cleanup call info for task {task_id}: {pop_error}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stop")
async def stop_agent(
    request: Request,
    task_id: uuid.UUID = Query(...),
    api_key: str = Depends(verify_api_key),
):
    """Cancel a running agent task."""
    orchestrator = _orchestrator(request)
    task_id_str = str(task_id)
    success = await orchestrator.stop_task(task_id_str)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task {task_id_str} not found")
    return {"status": "stopped", "task_id": task_id_str}


@router.get("/tools")
async def list_tools(request: Request, api_key: str = Depends(verify_api_key)):
    """List available tools."""
    orchestrator = _orchestrator(request)
    tools = orchestrator.get_available_tools()
    return {"tools": tools, "total": len(tools)}


@router.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models and routing strategy."""
    from app.agent.router import ModelRouter
    router_instance = ModelRouter()
    return {
        "models": router_instance.get_available_models(),
        "routing_strategy": "complexity_based",
    }
