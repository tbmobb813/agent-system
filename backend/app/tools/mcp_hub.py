"""
Persistent MCP sessions for SSE and stdio transports (official MCP Python SDK).

HTTP JSON-RPC (`/rpc`) stays in `mcp_client.MCPClient` — this hub is for servers
that require `sse_client` or `stdio_client` long-lived streams.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Optional

from app.utils.pillar_loader import get_pillar_config

logger = logging.getLogger(__name__)

_hub: Optional["McpConnectionHub"] = None


def set_mcp_hub(hub: Optional["McpConnectionHub"]) -> None:
    global _hub
    _hub = hub


def get_mcp_hub() -> Optional["McpConnectionHub"]:
    return _hub


def _format_call_tool_result(result: Any) -> dict[str, Any]:
    """Serialize mcp.types.CallToolResult for tool responses."""
    try:
        if getattr(result, "isError", False):
            return {
                "isError": True,
                "content": [c.model_dump() for c in (result.content or [])],
            }
        return {
            "isError": False,
            "content": [c.model_dump() for c in (result.content or [])],
            "structuredContent": getattr(result, "structuredContent", None),
        }
    except Exception as e:
        return {"isError": True, "parse_error": str(e), "raw": str(result)}


def _tools_to_registry_shape(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        try:
            schema = getattr(t, "inputSchema", None)
            if schema is not None and hasattr(schema, "model_dump"):
                sch: Any = schema.model_dump()
            elif isinstance(schema, dict):
                sch = schema
            else:
                sch = {}
            out.append(
                {
                    "name": t.name,
                    "description": (getattr(t, "description", None) or "")[:2000],
                    "inputSchema": sch,
                }
            )
        except Exception as e:
            logger.warning("Skipping MCP tool entry: %s", e)
    return out


@dataclass
class _SessionHolder:
    stop: asyncio.Event
    started: asyncio.Event
    session: Any
    task: Optional[asyncio.Task] = None
    connected: bool = False
    reconnect_attempts: int = 0
    last_error: Optional[str] = None
    last_connected_at: Optional[datetime] = None


class SseMcpRunner:
    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self._holder = _SessionHolder(
            stop=asyncio.Event(),
            started=asyncio.Event(),
            session=None,
        )

    async def _worker(self) -> None:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        backoff = 1.0
        while not self._holder.stop.is_set():
            try:
                async with sse_client(self.url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._holder.session = session
                        self._holder.connected = True
                        self._holder.last_error = None
                        self._holder.reconnect_attempts = 0
                        self._holder.last_connected_at = datetime.now(UTC)
                        self._holder.started.set()
                        backoff = 1.0
                        await self._holder.stop.wait()
                        break
            except Exception as e:
                self._holder.connected = False
                self._holder.session = None
                self._holder.reconnect_attempts += 1
                self._holder.last_error = str(e)
                logger.error(
                    "MCP SSE server %s (%s) failed: %s", self.name, self.url, e
                )
                self._holder.started.set()
                if self._holder.stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        self._holder.session = None
        self._holder.connected = False

    async def start(self) -> None:
        self._holder.task = asyncio.create_task(self._worker())
        try:
            await asyncio.wait_for(self._holder.started.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            self._holder.stop.set()
            if self._holder.task:
                self._holder.task.cancel()
            raise RuntimeError(f"MCP SSE server {self.name} timed out during connect")
        if self._holder.session is None:
            self._holder.stop.set()
            if self._holder.task:
                self._holder.task.cancel()
            raise RuntimeError(
                f"MCP SSE server {self.name} did not initialize a session"
            )

    async def stop(self) -> None:
        self._holder.stop.set()
        if self._holder.task:
            try:
                await asyncio.wait_for(self._holder.task, timeout=15.0)
            except Exception:
                self._holder.task.cancel()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._holder.session
        if session is None:
            return []
        lt = await session.list_tools()
        return _tools_to_registry_shape(list(lt.tools))

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        session = self._holder.session
        if session is None:
            raise RuntimeError(f"MCP SSE session not active: {self.name}")
        result = await session.call_tool(tool_name, arguments)
        return _format_call_tool_result(result)

    def health(self) -> dict[str, Any]:
        return {
            "connected": bool(
                self._holder.connected and self._holder.session is not None
            ),
            "reconnect_attempts": int(self._holder.reconnect_attempts),
            "last_error": self._holder.last_error,
            "last_connected_at": (
                self._holder.last_connected_at.isoformat()
                if self._holder.last_connected_at
                else None
            ),
            "transport": "sse",
            "target": self.url,
        }


class StdioMcpRunner:
    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = env
        self._holder = _SessionHolder(
            stop=asyncio.Event(),
            started=asyncio.Event(),
            session=None,
        )

    async def _worker(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from pathlib import Path

        merged_env = dict(os.environ)
        # Pydantic BaseSettings reads .env into settings objects but does not
        # populate os.environ, so stdio subprocesses would miss those vars.
        # Explicitly merge the .env file so MCP servers see all declared keys.
        try:
            from dotenv import dotenv_values

            _env_file = Path(__file__).resolve().parents[3] / "backend" / ".env"
            if not _env_file.is_file():
                _env_file = Path(__file__).resolve().parents[2] / ".env"
            if _env_file.is_file():
                for k, v in dotenv_values(_env_file).items():
                    if k not in merged_env and v is not None:
                        merged_env[k] = v
        except Exception:
            pass
        if self.env:
            merged_env.update({k: str(v) for k, v in self.env.items()})

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=merged_env,
        )
        backoff = 1.0
        while not self._holder.stop.is_set():
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._holder.session = session
                        self._holder.connected = True
                        self._holder.last_error = None
                        self._holder.reconnect_attempts = 0
                        self._holder.last_connected_at = datetime.now(UTC)
                        self._holder.started.set()
                        backoff = 1.0
                        await self._holder.stop.wait()
                        break
            except Exception as e:
                self._holder.connected = False
                self._holder.session = None
                self._holder.reconnect_attempts += 1
                self._holder.last_error = str(e)
                logger.error("MCP stdio server %s failed: %s", self.name, e)
                self._holder.started.set()
                if self._holder.stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        self._holder.session = None
        self._holder.connected = False

    async def start(self) -> None:
        self._holder.task = asyncio.create_task(self._worker())
        try:
            await asyncio.wait_for(self._holder.started.wait(), timeout=90.0)
        except asyncio.TimeoutError:
            self._holder.stop.set()
            if self._holder.task:
                self._holder.task.cancel()
            raise RuntimeError(f"MCP stdio server {self.name} timed out during connect")
        if self._holder.session is None:
            self._holder.stop.set()
            if self._holder.task:
                self._holder.task.cancel()
            raise RuntimeError(
                f"MCP stdio server {self.name} did not initialize a session"
            )

    async def stop(self) -> None:
        self._holder.stop.set()
        if self._holder.task:
            try:
                await asyncio.wait_for(self._holder.task, timeout=20.0)
            except Exception:
                self._holder.task.cancel()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._holder.session
        if session is None:
            return []
        lt = await session.list_tools()
        return _tools_to_registry_shape(list(lt.tools))

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        session = self._holder.session
        if session is None:
            raise RuntimeError(f"MCP stdio session not active: {self.name}")
        result = await session.call_tool(tool_name, arguments)
        return _format_call_tool_result(result)

    def health(self) -> dict[str, Any]:
        return {
            "connected": bool(
                self._holder.connected and self._holder.session is not None
            ),
            "reconnect_attempts": int(self._holder.reconnect_attempts),
            "last_error": self._holder.last_error,
            "last_connected_at": (
                self._holder.last_connected_at.isoformat()
                if self._holder.last_connected_at
                else None
            ),
            "transport": "stdio",
            "target": self.command,
        }


class McpConnectionHub:
    """Keeps SSE/stdio MCP servers alive for the app lifetime."""

    def __init__(self) -> None:
        self._runners: dict[str, Any] = {}

    @property
    def runners(self) -> dict[str, Any]:
        return self._runners

    async def start_from_pillars(self) -> None:
        cfg = get_pillar_config()
        mcp_cfg = (cfg.get("tools") or {}).get("mcp") or {}
        if not mcp_cfg.get("enabled"):
            return
        for srv in mcp_cfg.get("servers") or []:
            if not isinstance(srv, dict):
                continue
            name = str(srv.get("name") or "server").strip() or "server"
            transport = str(srv.get("transport") or "http_json").strip().lower()
            if transport in ("http", "http_json", "http_rpc", "rpc"):
                continue
            if name in self._runners:
                continue
            try:
                if transport == "sse":
                    url = str(srv.get("url") or "").strip()
                    if not url:
                        logger.warning("MCP SSE server %s skipped — no url", name)
                        continue
                    runner = SseMcpRunner(name, url)
                    await runner.start()
                    self._runners[name] = runner
                    logger.info("MCP SSE connected: %s", name)
                elif transport == "stdio":
                    cmd = str(srv.get("command") or "").strip()
                    args = srv.get("args") or []
                    if not cmd or not isinstance(args, list):
                        logger.warning(
                            "MCP stdio server %s skipped — need command and args[]",
                            name,
                        )
                        continue
                    env = srv.get("env") if isinstance(srv.get("env"), dict) else None
                    runner = StdioMcpRunner(name, cmd, [str(a) for a in args], env=env)
                    await runner.start()
                    self._runners[name] = runner
                    logger.info("MCP stdio started: %s", name)
                else:
                    logger.warning(
                        "Unknown MCP transport %r for server %s — skipped",
                        transport,
                        name,
                    )
            except Exception as e:
                logger.error("Failed to start MCP server %s: %s", name, e)

    async def stop(self) -> None:
        for r in list(self._runners.values()):
            try:
                await r.stop()
            except Exception as e:
                logger.debug("MCP runner stop: %s", e)
        self._runners.clear()

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        r = self._runners.get(server_name)
        if not r:
            return []
        return await r.list_tools()

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        r = self._runners.get(server_name)
        if not r:
            raise RuntimeError(f"No active MCP hub runner for server {server_name!r}")
        return await r.call_tool(tool_name, arguments)

    def health_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, runner in self._runners.items():
            detail: dict[str, Any]
            try:
                detail = runner.health() if hasattr(runner, "health") else {}
            except Exception as e:
                detail = {"last_error": str(e), "connected": False}
            rows.append(
                {
                    "tool": f"mcp:{name}",
                    "ok": bool(detail.get("connected")),
                    "detail": detail,
                }
            )
        return rows


async def register_hub_servers_into_registry(
    registry: Any, sanitize: Callable[[str, str], str]
) -> list[str]:
    """
    Attach tools from hub runners to ToolRegistry. Returns registered tool names.
    """
    hub = get_mcp_hub()
    if not hub:
        return []
    registered: list[str] = []
    for skey, runner in hub.runners.items():
        try:
            remote_tools = await runner.list_tools()
        except Exception as e:
            logger.warning("MCP hub list_tools failed for %s: %s", skey, e)
            continue
        for rt in remote_tools:
            tn = rt.get("name")
            if not tn:
                continue
            reg_name = sanitize(skey, str(tn))
            desc = str(rt.get("description") or f"MCP tool {tn} ({skey})")[:800]
            input_schema = rt.get("inputSchema") or {}
            oa = registry._json_schema_to_openai_params(input_schema)
            required = list(oa.get("required") or [])

            def _make_hub_handler(server: str, mcp_name: str):
                async def _handler(**kwargs: Any) -> dict[str, Any]:
                    h = get_mcp_hub()
                    if not h:
                        raise RuntimeError("MCP hub not available")
                    return await h.call_tool(server, mcp_name, kwargs)

                return _handler

            handler = _make_hub_handler(skey, str(tn))
            registry.register(
                name=reg_name,
                func=handler,
                description=desc,
                required_args=required,
            )
            registry._dynamic_schemas[reg_name] = {
                "type": "function",
                "function": {
                    "name": reg_name,
                    "description": desc,
                    "parameters": oa,
                },
            }
            registered.append(reg_name)
    return registered
