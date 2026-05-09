"""MCP HTTP client without real servers."""

from unittest.mock import MagicMock

import pytest

from app.tools.mcp_client import MCPClient

_PATCH = "app.tools.mcp_client.httpx.AsyncClient"


class _ACM:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self._handler

    async def __aexit__(self, *args):
        return None


def _client(handler):
    return _ACM(handler)


@pytest.mark.asyncio
async def test_mcp_health_check_ok(monkeypatch):
    h = MagicMock()

    async def get(url):
        r = MagicMock()
        r.status_code = 200
        return r

    h.get = get
    monkeypatch.setattr(_PATCH, lambda **_k: _client(h))

    out = await MCPClient("http://example.test").health_check()
    assert out["ok"] is True
    assert out["status_code"] == 200


@pytest.mark.asyncio
async def test_mcp_health_check_network_error(monkeypatch):
    def _boom(**_k):
        raise OSError("net")

    monkeypatch.setattr(_PATCH, _boom)
    out = await MCPClient("http://example.test").health_check()
    assert out["ok"] is False
    assert "net" in out["error"]


@pytest.mark.asyncio
async def test_mcp_call_tool_success(monkeypatch):
    h = MagicMock()

    async def post(url, json=None):
        r = MagicMock()
        r.status_code = 200
        r.json = lambda: {"result": {"x": 1}}
        r.raise_for_status = lambda: None
        return r

    h.post = post
    monkeypatch.setattr(_PATCH, lambda **_k: _client(h))

    data = await MCPClient("http://example.test").call_tool("t1", {"a": 2})
    assert data == {"x": 1}


@pytest.mark.asyncio
async def test_mcp_call_tool_rpc_error(monkeypatch):
    h = MagicMock()

    async def post(url, json=None):
        r = MagicMock()
        r.status_code = 200
        r.json = lambda: {"error": "bad"}
        r.raise_for_status = lambda: None
        return r

    h.post = post
    monkeypatch.setattr(_PATCH, lambda **_k: _client(h))

    with pytest.raises(RuntimeError, match="MCP tool call failed"):
        await MCPClient("http://example.test").call_tool("t1", {})


@pytest.mark.asyncio
async def test_mcp_list_tools_dict_and_string_result(monkeypatch):
    h = MagicMock()

    async def post(url, json=None):
        r = MagicMock()
        r.status_code = 200
        r.json = lambda: {"result": {"tools": [{"name": "a"}]}}
        r.raise_for_status = lambda: None
        return r

    h.post = post
    monkeypatch.setattr(_PATCH, lambda **_k: _client(h))
    assert await MCPClient("http://example.test").list_tools() == [{"name": "a"}]

    async def post2(url, json=None):
        r = MagicMock()
        r.status_code = 200
        r.json = lambda: {"result": "oops"}
        r.raise_for_status = lambda: None
        return r

    h.post = post2
    assert await MCPClient("http://example.test").list_tools() == []


@pytest.mark.asyncio
async def test_mcp_list_tools_rpc_error(monkeypatch):
    h = MagicMock()

    async def post(url, json=None):
        r = MagicMock()
        r.status_code = 200
        r.json = lambda: {"error": "nope"}
        r.raise_for_status = lambda: None
        return r

    h.post = post
    monkeypatch.setattr(_PATCH, lambda **_k: _client(h))

    with pytest.raises(RuntimeError, match="tools/list"):
        await MCPClient("http://example.test").list_tools()
