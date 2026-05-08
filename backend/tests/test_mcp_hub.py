import pytest

import app.tools.mcp_hub as mcp_hub
from app.tools.mcp_hub import McpConnectionHub, register_hub_servers_into_registry


class _FakeRunner:
    def __init__(self, tools=None, error: Exception | None = None):
        self._tools = tools or []
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        if self._error:
            raise self._error
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        return {"ok": True, "tool": tool_name, "arguments": arguments}


class _FakeRegistry:
    def __init__(self):
        self._dynamic_schemas = {}
        self._handlers = {}
        self.register_calls = []

    def _json_schema_to_openai_params(self, schema: dict):
        return {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }

    def register(self, *, name, func, description, required_args):
        self.register_calls.append(
            {
                "name": name,
                "description": description,
                "required_args": required_args,
            }
        )
        self._handlers[name] = func


@pytest.mark.asyncio
async def test_register_hub_servers_returns_empty_when_no_hub():
    registry = _FakeRegistry()
    mcp_hub.set_mcp_hub(None)

    out = await register_hub_servers_into_registry(registry, lambda s, t: f"{s}_{t}")

    assert out == []
    assert registry.register_calls == []


@pytest.mark.asyncio
async def test_register_hub_servers_skips_failing_server_and_registers_healthy():
    hub = McpConnectionHub()
    hub.runners["good"] = _FakeRunner(
        tools=[
            {
                "name": "search_issues",
                "description": "Search issues",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]
    )
    hub.runners["bad"] = _FakeRunner(error=RuntimeError("list failed"))
    mcp_hub.set_mcp_hub(hub)
    registry = _FakeRegistry()

    out = await register_hub_servers_into_registry(registry, lambda s, t: f"{s}_{t}")

    assert out == ["good_search_issues"]
    assert [c["name"] for c in registry.register_calls] == ["good_search_issues"]
    assert "good_search_issues" in registry._dynamic_schemas


@pytest.mark.asyncio
async def test_registered_hub_handler_raises_when_hub_gone():
    hub = McpConnectionHub()
    hub.runners["good"] = _FakeRunner(
        tools=[
            {"name": "echo", "description": "Echo", "inputSchema": {"type": "object"}}
        ]
    )
    mcp_hub.set_mcp_hub(hub)
    registry = _FakeRegistry()
    await register_hub_servers_into_registry(registry, lambda s, t: f"{s}_{t}")
    handler = registry._handlers["good_echo"]

    mcp_hub.set_mcp_hub(None)
    with pytest.raises(RuntimeError, match="MCP hub not available"):
        await handler(value="x")


@pytest.mark.asyncio
async def test_mcp_connection_hub_call_tool_raises_for_unknown_runner():
    hub = McpConnectionHub()
    with pytest.raises(RuntimeError, match="No active MCP hub runner"):
        await hub.call_tool("missing", "echo", {})


def test_mcp_connection_hub_health_snapshot_includes_runner_state():
    class _HealthRunner:
        def health(self):
            return {
                "connected": True,
                "reconnect_attempts": 2,
                "last_error": None,
                "transport": "sse",
            }

    hub = McpConnectionHub()
    hub.runners["server_a"] = _HealthRunner()

    rows = hub.health_snapshot()
    assert len(rows) == 1
    assert rows[0]["tool"] == "mcp:server_a"
    assert rows[0]["ok"] is True
    assert rows[0]["detail"]["reconnect_attempts"] == 2
