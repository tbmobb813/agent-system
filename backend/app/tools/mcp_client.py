"""
Minimal MCP client for external MCP-compatible servers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, server_url: str, timeout_seconds: float = 20.0):
        self.server_url = server_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def health_check(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(f"{self.server_url}/health")
                return {"ok": resp.status_code < 400, "status_code": resp.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(f"{self.server_url}/rpc", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP tool call failed: {data['error']}")
            return data.get("result", {})

    async def list_tools(self) -> list[dict[str, Any]]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {},
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(f"{self.server_url}/rpc", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP tools/list failed: {data['error']}")
            result = data.get("result", {})
            return result.get("tools", []) if isinstance(result, dict) else []
