"""Smoke tests for MCP stdio runner wiring (no live MCP server)."""

from app.tools.mcp_hub import StdioMcpRunner


def test_stdio_runner_constructible():
    r = StdioMcpRunner("test_server", "python3", ["-c", "pass"])
    assert r.name == "test_server"
    assert r.command == "python3"
    assert r.args == ["-c", "pass"]
