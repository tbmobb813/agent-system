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
import yaml

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import settings
from app.models import (
    AgentRequest,
    AgentResponse,
    WorkflowRunRequest,
    McpServerCreate,
    McpServerUpdate,
    McpServerTest,
)
from app.utils.auth import verify_api_key
from app.utils.limiter import limiter
from app.utils.streaming import format_sse_event
from app.utils.pillar_loader import get_pillar_config, pillars_file_path
from app.database import execute, fetch
from app import database as _db
from app.routes.schedules import router as schedules_router
from app.tools.mcp_hub import McpConnectionHub, set_mcp_hub
from app.tools.mcp_hub import SseMcpRunner, StdioMcpRunner
from app.tools.mcp_client import MCPClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])
router.include_router(schedules_router)


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


def _runtime(request: Request):
    runtime = getattr(request.app.state, "orchestration_runtime", None)
    if not runtime:
        raise HTTPException(
            status_code=503, detail="Orchestration runtime not initialized"
        )
    return runtime


async def _record_latency_metric(
    *,
    endpoint: str,
    duration_ms: int,
    status: str,
    task_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Best-effort latency metric persistence (never raises)."""
    if not _db.db_pool:
        return
    try:
        await execute(
            """
            INSERT INTO latency_metrics (endpoint, duration_ms, status, task_id, user_id, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            endpoint,
            duration_ms,
            status,
            task_id,
            user_id,
        )
    except Exception as e:
        # Keep request paths resilient even if metrics table is missing.
        logger.debug(f"Could not persist latency metric: {e}")


def _schedule_followup_suggestions(
    *,
    query: str,
    result: str,
    task_id: str | None,
    user_id: str | None,
) -> None:
    """Fire-and-forget follow-up suggestion generation for completed tasks."""
    if not task_id:
        return
    try:
        from app.agent.followup import generate_followup_suggestions

        asyncio.create_task(
            generate_followup_suggestions(
                task_id=task_id,
                query=query,
                result=result,
                user_id=user_id,
            )
        )
    except Exception as e:
        logger.debug(f"Could not schedule followup suggestions: {e}")


def _schedule_quality_scoring(
    *,
    query: str,
    response: str,
    task_id: str | None,
    user_id: str | None,
    model_used: str | None,
) -> None:
    """Fire-and-forget quality scoring for completed responses."""
    try:
        from app.agent.quality import score_response_quality

        asyncio.create_task(
            score_response_quality(
                query=query,
                response=response,
                task_id=task_id,
                user_id=user_id,
                model_used=model_used,
            )
        )
    except Exception as e:
        logger.debug(f"Could not schedule quality scoring: {e}")


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
    remaining = (
        settings.OPENROUTER_BUDGET_MONTHLY - await cost_tracker.get_spent_month()
    )

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
    run_status = "completed"
    try:
        result, conv_id = await orchestrator.run(
            query=body.query,
            context=body.context,
            tools=body.tools,
            user_id=body.user_id,
            max_iterations=body.max_iterations,
            conversation_id=body.conversation_id,
            reasoning_effort=body.reasoning_effort,
        )
    except Exception:
        run_status = "failed"
        raise
    finally:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await _record_latency_metric(
            endpoint="/agent/run",
            duration_ms=elapsed_ms,
            status=run_status,
            user_id=body.user_id,
        )
    elapsed = elapsed_ms / 1000.0

    model_used = cost_tracker.get_last_model(task_id=None)
    _schedule_quality_scoring(
        query=body.query,
        response=result,
        task_id=None,
        user_id=body.user_id,
        model_used=model_used,
    )

    return AgentResponse(
        query=body.query,
        result=result,
        status="completed",
        cost=await cost_tracker.get_last_call_cost(task_id=None),
        model_used=model_used,
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
                status,
                datetime.utcnow(),
                task_id,
            )
        except Exception as e:
            logger.warning(f"Could not update task status: {e}")

    async def generate():
        _stream = None
        stream_status = "completed"
        try:
            estimated_cost = await cost_tracker.estimate_cost(body.query)
            remaining = (
                settings.OPENROUTER_BUDGET_MONTHLY
                - await cost_tracker.get_spent_month()
            )

            if estimated_cost > remaining:
                stream_status = "budget_exceeded"
                yield format_sse_event(
                    {
                        "type": "error",
                        "error": "Insufficient budget",
                        "spent": await cost_tracker.get_spent_month(),
                        "budget": settings.OPENROUTER_BUDGET_MONTHLY,
                    }
                )
                return

            yield format_sse_event(
                {"type": "status", "content": "initializing", "task_id": task_id}
            )

            # Pre-insert task as running
            if _db.db_pool:
                try:
                    await execute(
                        """
                        INSERT INTO tasks (id, user_id, query, status, cost, created_at)
                        VALUES ($1, $2, $3, 'running', 0, $4)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        task_id,
                        user_id,
                        body.query,
                        started_at,
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
                reasoning_effort=body.reasoning_effort,
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
                    stream_status = "failed"
                    await _persist_terminal_status(status)
                    if _stream is not None:
                        try:
                            await _stream.aclose()
                        except Exception as close_error:
                            logger.debug(
                                f"Failed to close timed out stream: {close_error}"
                            )
                    yield format_sse_event(
                        {
                            "type": "error",
                            "error": f"Run timed out after {settings.MAX_STREAM_SECONDS}s",
                        }
                    )
                    return

                data = event.model_dump(mode="json")
                # Always attach task id so the client can rate the correct row after a run completes.
                data["task_id"] = str(task_id)
                if event.type.value == "text_delta" and event.content:
                    result_parts.append(event.content)
                    if event.model and not model_used:
                        model_used = event.model
                if event.type.value == "error":
                    status = "failed"
                    stream_status = "failed"
                if event.type.value == "status" and event.content == "stopped by user":
                    status = "stopped"
                    stream_status = "stopped"
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
                    _schedule_quality_scoring(
                        query=body.query,
                        response="".join(result_parts),
                        task_id=task_id,
                        user_id=user_id,
                        model_used=model_used,
                    )
                    _schedule_followup_suggestions(
                        query=body.query,
                        result="".join(result_parts),
                        task_id=task_id,
                        user_id=user_id,
                    )
                yield format_sse_event(data)

            # Stream ended without DONE (stopped or interrupted) — update DB
            if not got_done:
                if status == "completed":
                    stream_status = "incomplete"
                await _persist_terminal_status(status)

        except asyncio.CancelledError:
            stream_status = "cancelled"
            if _stream is not None:
                try:
                    await _stream.aclose()
                except Exception as close_error:
                    logger.debug(f"Failed to close cancelled stream: {close_error}")
            raise
        except Exception as e:
            stream_status = "failed"
            logger.error(f"Stream error: {e}", exc_info=True)
            # PermissionError must be checked before OSError (it is a subclass of OSError)
            if isinstance(e, PermissionError):
                error_code = "auth_error"
            elif isinstance(e, (ConnectionError, OSError)):
                error_code = "connection_error"
            elif isinstance(e, ValueError):
                error_code = "invalid_request"
            else:
                error_code = "stream_error"
            yield format_sse_event(
                {"type": "error", "error": error_code, "task_id": task_id}
            )
        finally:
            elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
            await _record_latency_metric(
                endpoint="/agent/stream",
                duration_ms=elapsed_ms,
                status=stream_status,
                task_id=task_id,
                user_id=user_id,
            )
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
                    logger.debug(
                        f"Failed to cleanup call info for task {task_id}: {pop_error}"
                    )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/enqueue")
@limiter.limit("20/minute")
async def enqueue_agent_task(
    request: Request,
    body: AgentRequest,
    api_key: str = Depends(verify_api_key),
):
    """Queue a deferred task for background execution."""
    runtime = _runtime(request)
    cost_tracker = _cost_tracker(request)
    estimated_cost = await cost_tracker.estimate_cost(body.query)
    remaining = (
        settings.OPENROUTER_BUDGET_MONTHLY - await cost_tracker.get_spent_month()
    )
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

    task_id = str(uuid.uuid4())
    if _db.db_pool:
        try:
            await execute(
                """
                INSERT INTO tasks (id, user_id, query, status, cost, created_at)
                VALUES ($1, $2, $3, 'queued', 0, $4)
                ON CONFLICT (id) DO NOTHING
                """,
                task_id,
                body.user_id,
                body.query,
                datetime.utcnow(),
            )
        except Exception as e:
            logger.warning(f"Could not pre-insert queued task: {e}")
    await runtime.enqueue_task(
        {
            "task_id": task_id,
            "query": body.query,
            "context": body.context,
            "tools": body.tools,
            "user_id": body.user_id,
            "max_iterations": body.max_iterations,
            "conversation_id": body.conversation_id,
            "reasoning_effort": body.reasoning_effort,
        }
    )
    qs = await runtime.pending_queue_size()
    return {
        "status": "queued",
        "task_id": task_id,
        "queue_size": qs,
    }


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


@router.get("/suggestions/{task_id}")
@limiter.limit("60/minute")
async def get_task_suggestions(
    request: Request,
    task_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Retrieve follow-up suggestions for a completed task (generated asynchronously)."""
    from app.database import fetchrow as db_fetchrow

    row = await db_fetchrow(
        "SELECT suggestions FROM task_suggestions WHERE task_id = $1", task_id
    )
    if not row:
        return {"task_id": task_id, "suggestions": [], "ready": False}
    return {"task_id": task_id, "suggestions": row["suggestions"], "ready": True}


@router.get("/tools/health")
@limiter.limit("60/minute")
async def agent_tools_health(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Readiness snapshot for built-in tools and configured MCP servers."""
    orchestrator = _orchestrator(request)
    checks = await orchestrator.tools.tool_health_snapshot()
    return {
        "checks": checks,
        "healthy_count": sum(1 for c in checks if c.get("ok")),
        "total": len(checks),
    }


def _get_mcp_servers_config(cfg: dict) -> list:
    tools = cfg.setdefault("tools", {})
    mcp = tools.setdefault("mcp", {})
    mcp["enabled"] = True
    servers = mcp.setdefault("servers", [])
    if not isinstance(servers, list):
        raise HTTPException(status_code=500, detail="Invalid tools.mcp.servers format")
    return servers


def _build_mcp_server_entry(
    *,
    transport: str,
    url: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    entry: dict = {"transport": transport}
    if transport in ("http_json", "sse"):
        if not url or not str(url).strip():
            raise HTTPException(
                status_code=400, detail="url is required for http_json/sse transport"
            )
        entry["url"] = str(url).strip()
    elif transport == "stdio":
        if not command or not str(command).strip():
            raise HTTPException(
                status_code=400, detail="command is required for stdio transport"
            )
        if not args or len(args) == 0:
            raise HTTPException(
                status_code=400, detail="args[] is required for stdio transport"
            )
        entry["command"] = str(command).strip()
        entry["args"] = [str(a) for a in args]
        if env:
            entry["env"] = {str(k): str(v) for k, v in env.items()}
    else:
        raise HTTPException(
            status_code=400, detail=f"Unsupported transport: {transport}"
        )
    return entry


def _persist_pillars_config(path, cfg: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update pillars config: {e}"
        )


async def _reload_mcp_runtime(request: Request) -> None:
    app = request.app
    old_hub = getattr(app.state, "mcp_hub", None)
    try:
        if old_hub:
            await old_hub.stop_all()
    except Exception as e:
        logger.debug("Previous MCP hub stop failed: %s", e)

    hub = McpConnectionHub()
    await hub.start_from_pillars()
    set_mcp_hub(hub)
    app.state.mcp_hub = hub
    await _orchestrator(request).tools.load_mcp_tools()


@router.get("/mcp/servers")
@limiter.limit("60/minute")
async def list_mcp_servers(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    cfg = get_pillar_config(force_reload=True)
    if not cfg:
        return {"servers": [], "total": 0}
    servers = _get_mcp_servers_config(cfg)
    out = [s for s in servers if isinstance(s, dict)]
    return {"servers": out, "total": len(out)}


@router.post("/mcp/servers")
@limiter.limit("20/minute")
async def add_mcp_server(
    request: Request,
    body: McpServerCreate,
    api_key: str = Depends(verify_api_key),
):
    """Persist a new MCP server entry and refresh MCP runtime registrations."""
    path = pillars_file_path()
    cfg = get_pillar_config(force_reload=True)
    if not cfg:
        raise HTTPException(status_code=500, detail="agent_pillars.yaml is unavailable")

    servers = _get_mcp_servers_config(cfg)

    name = body.name.strip()
    if any(
        isinstance(s, dict) and str(s.get("name", "")).strip().lower() == name.lower()
        for s in servers
    ):
        raise HTTPException(
            status_code=409, detail=f"MCP server '{name}' already exists"
        )

    entry = {
        "name": name,
        **_build_mcp_server_entry(
            transport=body.transport,
            url=body.url,
            command=body.command,
            args=body.args,
            env=body.env,
        ),
    }

    servers.append(entry)
    _persist_pillars_config(path, cfg)
    await _reload_mcp_runtime(request)

    return {"status": "added", "server": entry}


@router.put("/mcp/servers/{server_name}")
@limiter.limit("20/minute")
async def update_mcp_server(
    request: Request,
    server_name: str,
    body: McpServerUpdate,
    api_key: str = Depends(verify_api_key),
):
    path = pillars_file_path()
    cfg = get_pillar_config(force_reload=True)
    if not cfg:
        raise HTTPException(status_code=500, detail="agent_pillars.yaml is unavailable")
    servers = _get_mcp_servers_config(cfg)
    target = server_name.strip().lower()
    idx = next(
        (
            i
            for i, s in enumerate(servers)
            if isinstance(s, dict) and str(s.get("name", "")).strip().lower() == target
        ),
        -1,
    )
    if idx < 0:
        raise HTTPException(
            status_code=404, detail=f"MCP server '{server_name}' not found"
        )

    original_name = str(servers[idx].get("name", "")).strip() or server_name.strip()
    servers[idx] = {
        "name": original_name,
        **_build_mcp_server_entry(
            transport=body.transport,
            url=body.url,
            command=body.command,
            args=body.args,
            env=body.env,
        ),
    }
    _persist_pillars_config(path, cfg)
    await _reload_mcp_runtime(request)
    return {"status": "updated", "server": servers[idx]}


@router.delete("/mcp/servers/{server_name}")
@limiter.limit("20/minute")
async def delete_mcp_server(
    request: Request,
    server_name: str,
    api_key: str = Depends(verify_api_key),
):
    path = pillars_file_path()
    cfg = get_pillar_config(force_reload=True)
    if not cfg:
        raise HTTPException(status_code=500, detail="agent_pillars.yaml is unavailable")
    servers = _get_mcp_servers_config(cfg)
    target = server_name.strip().lower()
    new_servers = [
        s
        for s in servers
        if not (
            isinstance(s, dict) and str(s.get("name", "")).strip().lower() == target
        )
    ]
    if len(new_servers) == len(servers):
        raise HTTPException(
            status_code=404, detail=f"MCP server '{server_name}' not found"
        )
    cfg["tools"]["mcp"]["servers"] = new_servers
    _persist_pillars_config(path, cfg)
    await _reload_mcp_runtime(request)
    return {"status": "deleted", "name": server_name}


@router.post("/mcp/servers/test")
@limiter.limit("30/minute")
async def test_mcp_server_config(
    request: Request,
    body: McpServerTest,
    api_key: str = Depends(verify_api_key),
):
    """Probe an MCP server config without saving it."""
    spec = _build_mcp_server_entry(
        transport=body.transport,
        url=body.url,
        command=body.command,
        args=body.args,
        env=body.env,
    )
    transport = spec["transport"]
    if transport == "http_json":
        health = await MCPClient(str(spec["url"])).health_check()
        if not health.get("ok"):
            return {"ok": False, "transport": transport, "detail": health}
        try:
            tools = await MCPClient(str(spec["url"])).list_tools()
            return {
                "ok": True,
                "transport": transport,
                "tools_count": len(tools),
                "detail": health,
            }
        except Exception as e:
            return {"ok": False, "transport": transport, "detail": str(e)}
    if transport == "sse":
        runner = SseMcpRunner("__probe__", str(spec["url"]))
        try:
            await asyncio.wait_for(runner.start(), timeout=25.0)
            tools = await runner.list_tools()
            return {
                "ok": True,
                "transport": transport,
                "tools_count": len(tools),
                "detail": runner.health(),
            }
        except Exception as e:
            return {"ok": False, "transport": transport, "detail": str(e)}
        finally:
            try:
                await runner.stop()
            except Exception:
                pass
    runner = StdioMcpRunner(
        "__probe__",
        str(spec["command"]),
        list(spec["args"]),
        spec.get("env"),
    )
    try:
        await asyncio.wait_for(runner.start(), timeout=30.0)
        tools = await runner.list_tools()
        return {
            "ok": True,
            "transport": transport,
            "tools_count": len(tools),
            "detail": runner.health(),
        }
    except Exception as e:
        return {"ok": False, "transport": transport, "detail": str(e)}
    finally:
        try:
            await runner.stop()
        except Exception:
            pass


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


@router.get("/stats")
@limiter.limit("30/minute")
async def agent_latency_stats(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    api_key: str = Depends(verify_api_key),
):
    """p50/p95/p99 latency by endpoint from ``latency_metrics`` (if table exists)."""
    if not _db.db_pool:
        return {
            "window_days": days,
            "latency_by_endpoint": [],
            "note": "database_unavailable",
        }
    try:
        rows = await fetch(
            """
            SELECT endpoint,
                   percentile_disc(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
                   percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
                   percentile_disc(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99_ms,
                   COUNT(*)::bigint AS n
            FROM latency_metrics
            WHERE created_at >= (NOW() - ($1::int * INTERVAL '1 day'))
            GROUP BY endpoint
            ORDER BY endpoint
            """,
            days,
        )
    except Exception as e:
        logger.debug("latency stats query failed: %s", e)
        return {
            "window_days": days,
            "latency_by_endpoint": [],
            "note": "latency_metrics_unavailable",
        }

    return {
        "window_days": days,
        "latency_by_endpoint": [
            {
                "endpoint": r["endpoint"],
                "p50_ms": float(r["p50_ms"]) if r["p50_ms"] is not None else None,
                "p95_ms": float(r["p95_ms"]) if r["p95_ms"] is not None else None,
                "p99_ms": float(r["p99_ms"]) if r["p99_ms"] is not None else None,
                "n": int(r["n"]),
            }
            for r in rows
        ],
    }


@router.get("/dead-letter")
@limiter.limit("20/minute")
async def list_dead_letter_tasks(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    user_id: str | None = Query(None),
    include_payload: bool = Query(False),
    api_key: str = Depends(verify_api_key),
):
    """List failed deferred tasks captured in failed_tasks."""
    if not _db.db_pool:
        return {"items": [], "total": 0, "note": "database_unavailable"}
    try:
        if user_id:
            rows = await fetch(
                """
                SELECT id, task_id, error, payload, created_at
                FROM failed_tasks
                WHERE COALESCE(payload->>'user_id', '') = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
        else:
            rows = await fetch(
                """
                SELECT id, task_id, error, payload, created_at
                FROM failed_tasks
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
    except Exception as e:
        logger.debug("dead-letter list query failed: %s", e)
        return {"items": [], "total": 0, "note": "failed_tasks_unavailable"}

    items = []
    for r in rows:
        payload = r["payload"] if include_payload else None
        items.append(
            {
                "id": str(r["id"]),
                "task_id": str(r["task_id"]) if r["task_id"] else None,
                "error": str(r["error"]),
                "created_at": (
                    r["created_at"].isoformat() if r["created_at"] is not None else None
                ),
                "payload": payload,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/dead-letter/{failed_task_id}/replay")
@limiter.limit("10/minute")
async def replay_dead_letter_task(
    request: Request,
    failed_task_id: uuid.UUID,
    keep_record: bool = Query(False),
    api_key: str = Depends(verify_api_key),
):
    """Re-enqueue a dead-letter payload for retry."""
    runtime = _runtime(request)
    try:
        out = await runtime.replay_failed_task(
            str(failed_task_id),
            delete_immediately=not keep_record,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.warning("dead-letter replay failed: %s", e)
        raise HTTPException(status_code=500, detail="dead_letter_replay_failed")
    return out


@router.get("/workflow-suggestions")
@limiter.limit("30/minute")
async def get_workflow_suggestions(
    request: Request,
    min_occurrences: int = 3,
    api_key: str = Depends(verify_api_key),
):
    """Return recurring task patterns that are candidates for workflow automation."""
    from app.agent.workflow_suggestions import get_workflow_suggestions as _get_suggestions

    return {"suggestions": await _get_suggestions(min_occurrences=min_occurrences)}


@router.get("/skill-chains")
@limiter.limit("60/minute")
async def list_skill_chains(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """List all defined skill chains."""
    from app.agent.skill_composer import list_chains
    return {"chains": await list_chains()}


@router.post("/skill-chains")
@limiter.limit("30/minute")
async def create_skill_chain(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Create a new skill chain."""
    from app.agent.skill_composer import create_chain
    body = await request.json()
    name = str(body.get("name") or "").strip()
    task_type = str(body.get("task_type") or "general").strip()
    steps = body.get("steps") or []
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=400, detail="steps must be a non-empty list")
    try:
        chain = await create_chain(
            name=name,
            task_type=task_type,
            steps=steps,
            description=str(body.get("description") or ""),
            trigger_keywords=body.get("trigger_keywords") or [],
        )
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    return chain


@router.delete("/skill-chains/{chain_id}")
@limiter.limit("30/minute")
async def delete_skill_chain(
    request: Request,
    chain_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Delete a skill chain by ID."""
    from app.agent.skill_composer import delete_chain
    deleted = await delete_chain(chain_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill chain not found")
    return {"deleted": chain_id}


@router.post("/skill-chains/auto-generate")
@limiter.limit("10/minute")
async def auto_generate_skill_chains(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Promote top tool_recommendations into skill chains automatically."""
    from app.agent.skill_composer import auto_generate_chains
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    min_occ = int((body or {}).get("min_occurrences") or 5)
    created = await auto_generate_chains(min_occurrences=min_occ)
    return {"created": created, "count": len(created)}


@router.post("/workflows/{name}/run")
@limiter.limit("10/minute")
async def run_declared_workflow(
    request: Request,
    name: str,
    body: WorkflowRunRequest,
    api_key: str = Depends(verify_api_key),
):
    """Run a YAML workflow from ``backend/data/workflows/{name}.yaml``."""
    from app.agent.workflows import run_named_workflow

    orchestrator = _orchestrator(request)
    try:
        return await run_named_workflow(orchestrator, name, user_id=body.user_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Workflow {name!r} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
