"""
Tool Registry - Manages all available tools the agent can use.
"""

import asyncio
import json
import logging
import os
import re
import httpx
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from inspect import signature
from urllib.parse import urlparse

from app.config import settings
from app.utils.http_headers import redact_response_headers
from app.utils.truncate import truncate_head
from app.utils.url_safety import (
    validate_agent_outbound_url,
    validate_browser_automation_host,
)

logger = logging.getLogger(__name__)


class Tool:
    """Definition of a single tool."""

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        required_args: list[str] = None,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.required_args = required_args or []
        self.signature = signature(func)

    async def call(self, **kwargs) -> Any:
        """Call the tool with given arguments."""
        try:
            # Support both async and sync functions
            import inspect

            if inspect.iscoroutinefunction(self.func):
                return await self.func(**kwargs)
            else:
                return self.func(**kwargs)
        except TypeError as e:
            raise ValueError(f"Invalid arguments for {self.name}: {e}")


class ToolRegistry:
    """
    Registry of all available tools.
    Tools are functions that the agent can call to perform actions.
    """

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._dynamic_schemas: Dict[str, dict] = {}
        self._mcp_tool_names: list[str] = []
        self._sub_agent_registered: bool = False
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """Register built-in tools."""
        # Web Search
        self.register(
            name="web_search",
            func=self._web_search,
            description="Search the web for information. Returns top results with titles, URLs, and snippets.",
            required_args=["query"],
        )

        # Browser Automation
        self.register(
            name="browser_automation",
            func=self._browser_automation,
            description="Automate browser tasks: navigate pages, extract data, fill forms, take screenshots.",
            required_args=["action"],
        )

        # File Operations
        self.register(
            name="file_operations",
            func=self._file_operations,
            description="Read, write, and manage files within the workspace.",
            required_args=["operation"],
        )

        # Code Execution
        self.register(
            name="code_execution",
            func=self._code_execution,
            description="Execute code in a secure sandbox and return the output.",
            required_args=["code"],
        )

        # API Calling
        self.register(
            name="api_call",
            func=self._api_call,
            description="Make HTTP requests to external APIs.",
            required_args=["url", "method"],
        )

        # Document search
        self.register(
            name="search_documents",
            func=self._search_documents,
            description="Search through uploaded documents for relevant information.",
            required_args=["query"],
        )

        # GitHub connector
        self.register(
            name="github",
            func=self._github,
            description=(
                "Interact with GitHub: search repos, read issues and PRs, view files, "
                "list commits, create issues, and comment. Requires GITHUB_TOKEN."
            ),
            required_args=["action"],
        )

    @staticmethod
    def _json_schema_to_openai_params(schema: Any) -> dict:
        if not isinstance(schema, dict) or not schema:
            return {"type": "object", "properties": {}, "required": []}
        if schema.get("type") == "object":
            return {
                "type": "object",
                "properties": schema.get("properties") or {},
                "required": list(schema.get("required") or []),
            }
        return {"type": "object", "properties": {"_value": schema}, "required": []}

    @staticmethod
    def _sanitize_mcp_function_name(server_key: str, tool_name: str) -> str:
        raw = re.sub(r"[^a-zA-Z0-9_]", "_", f"mcp_{server_key}_{tool_name}")
        if raw and raw[0].isdigit():
            raw = "mcp_" + raw
        return raw[:80]

    async def load_mcp_tools(self) -> None:
        """
        Register tools from agent_pillars.yaml tools.mcp.servers:
        - http_json (default): POST {url}/rpc
        - sse / stdio: persistent sessions via app.tools.mcp_hub (start hub first)
        """
        from app.tools.mcp_client import MCPClient
        from app.tools.mcp_hub import register_hub_servers_into_registry
        from app.utils.pillar_loader import get_pillar_config

        for name in self._mcp_tool_names:
            self.tools.pop(name, None)
            self._dynamic_schemas.pop(name, None)
        self._mcp_tool_names = []

        cfg = get_pillar_config()
        mcp_cfg = (cfg.get("tools") or {}).get("mcp") or {}
        if not mcp_cfg.get("enabled"):
            return

        for srv in mcp_cfg.get("servers") or []:
            if not isinstance(srv, dict):
                continue
            skey = str(srv.get("name") or "server").strip() or "server"
            transport = str(srv.get("transport") or "http_json").strip().lower()
            if transport in ("sse", "stdio"):
                continue
            if transport not in ("http", "http_json", "http_rpc", "rpc"):
                logger.warning(
                    "Unknown MCP transport %r for %s — skipping HTTP path",
                    transport,
                    skey,
                )
                continue

            base_url = str(srv.get("url") or "").strip().rstrip("/")
            if not base_url:
                logger.warning("MCP HTTP server %s skipped — no url", skey)
                continue

            client = MCPClient(base_url)
            try:
                remote_tools = await client.list_tools()
            except Exception as e:
                logger.warning(
                    "MCP tools/list failed for %s (%s): %s", skey, base_url, e
                )
                continue

            for rt in remote_tools:
                if not isinstance(rt, dict):
                    continue
                tn = rt.get("name")
                if not tn:
                    continue
                reg_name = self._sanitize_mcp_function_name(skey, str(tn))
                if reg_name in self.tools:
                    reg_name = f"{reg_name}_alt"

                desc = str(rt.get("description") or f"MCP tool {tn} ({skey})")[:800]
                input_schema = rt.get("inputSchema") or rt.get("input_schema") or {}
                oa = self._json_schema_to_openai_params(input_schema)
                required = list(oa.get("required") or [])

                def _make_handler(url: str, mcp_name: str):
                    async def _handler(**kwargs: Any) -> dict[str, Any]:
                        cl = MCPClient(url)
                        return await cl.call_tool(mcp_name, kwargs)

                    return _handler

                handler = _make_handler(base_url, str(tn))
                self.register(
                    name=reg_name,
                    func=handler,
                    description=desc,
                    required_args=required,
                )
                self._mcp_tool_names.append(reg_name)
                self._dynamic_schemas[reg_name] = {
                    "type": "function",
                    "function": {
                        "name": reg_name,
                        "description": desc,
                        "parameters": oa,
                    },
                }

        try:
            hub_more = await register_hub_servers_into_registry(
                self, self._sanitize_mcp_function_name
            )
            self._mcp_tool_names.extend(hub_more)
        except Exception as e:
            logger.warning("MCP hub registration failed: %s", e)

        if self._mcp_tool_names:
            logger.info("Registered %s MCP tool(s)", len(self._mcp_tool_names))

    def register_sub_agent_tool(self, orchestrator: Any) -> None:
        """Expose nested agent runs as delegate_sub_agent (call once after orchestrator exists)."""
        if self._sub_agent_registered:
            return
        self._sub_agent_registered = True

        async def _delegate(*, query: str, depth: int = 1) -> str:
            out = await orchestrator.run_sub_agent(
                query=query,
                depth=int(depth),
                max_depth=2,
            )
            return json.dumps(out, ensure_ascii=False)

        desc = (
            "Delegate a focused sub-task to a nested agent run (fresh ReAct loop, depth-limited). "
            "Use for isolated research, coding, or analysis that should not pollute the main thread."
        )
        self.register(
            name="delegate_sub_agent",
            func=_delegate,
            description=desc,
            required_args=["query"],
        )
        self._dynamic_schemas["delegate_sub_agent"] = {
            "type": "function",
            "function": {
                "name": "delegate_sub_agent",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Self-contained sub-task for the nested agent",
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Nesting depth (1–2)",
                            "default": 1,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def tool_health_snapshot(self) -> list[dict[str, Any]]:
        """Lightweight readiness checks for builtins + configured MCP servers."""
        from app.tools.mcp_client import MCPClient
        from app.tools.mcp_hub import get_mcp_hub
        from app.utils.pillar_loader import get_pillar_config

        rows: list[dict[str, Any]] = []

        # web_search — SearXNG or Brave
        searx_ok = False
        searx_err = ""
        try:
            async with httpx.AsyncClient(timeout=5.0) as hc:
                r = await hc.get(
                    f"{settings.SEARXNG_URL}/search",
                    params={"q": "__health__", "format": "json"},
                )
                searx_ok = r.status_code < 500
        except Exception as e:
            searx_err = str(e)
        brave_configured = bool(settings.BRAVE_SEARCH_API_KEY)
        ws_ok = searx_ok or brave_configured
        rows.append(
            {
                "tool": "web_search",
                "ok": ws_ok,
                "detail": (
                    "searxng"
                    if searx_ok
                    else (
                        "brave_key_set"
                        if brave_configured
                        else searx_err or "no_provider"
                    )
                ),
            }
        )

        browser_ok = False
        berr = ""
        try:
            from playwright.async_api import async_playwright  # noqa: F401

            browser_ok = True
        except Exception as e:
            berr = str(e)
        rows.append(
            {
                "tool": "browser_automation",
                "ok": browser_ok,
                "detail": "playwright_import" if browser_ok else berr,
            }
        )

        rows.append(
            {
                "tool": "code_execution",
                "ok": bool(settings.E2B_API_KEY),
                "detail": (
                    "e2b_configured" if settings.E2B_API_KEY else "E2B_API_KEY unset"
                ),
            }
        )

        ws_path = Path(settings.AGENT_WORKSPACE_DIR).expanduser()
        try:
            ws_path.mkdir(parents=True, exist_ok=True)
            w_ok = os.access(ws_path, os.W_OK)
        except Exception:
            w_ok = False
        rows.append({"tool": "file_operations", "ok": w_ok, "detail": str(ws_path)})

        rows.append({"tool": "api_call", "ok": True, "detail": "always_available"})

        doc_ok = bool(settings.OPENAI_API_KEY)
        rows.append(
            {
                "tool": "search_documents",
                "ok": doc_ok,
                "detail": (
                    "openai_embeddings" if doc_ok else "fulltext_only_without_openai"
                ),
            }
        )

        gh_ok = bool(settings.GITHUB_TOKEN)
        rows.append(
            {
                "tool": "github",
                "ok": gh_ok,
                "detail": "token_configured" if gh_ok else "GITHUB_TOKEN unset",
            }
        )

        if "delegate_sub_agent" in self.tools:
            rows.append(
                {"tool": "delegate_sub_agent", "ok": True, "detail": "registered"}
            )

        mcp_cfg = (get_pillar_config().get("tools") or {}).get("mcp") or {}
        if mcp_cfg.get("enabled"):
            servers = [
                s
                for s in (mcp_cfg.get("servers") or [])
                if isinstance(s, dict)
                and s.get("transport", "http_json") == "http_json"
                and str(s.get("url") or "").strip()
            ]

            async def _check_mcp(srv: dict) -> dict:
                skey = str(srv.get("name") or "server")
                url = str(srv.get("url") or "").strip().rstrip("/")
                try:
                    h = await MCPClient(url).health_check()
                    return {"tool": f"mcp:{skey}", "ok": bool(h.get("ok")), "detail": h}
                except Exception as e:
                    return {"tool": f"mcp:{skey}", "ok": False, "detail": str(e)}

            mcp_results = await asyncio.gather(*[_check_mcp(s) for s in servers])
            rows.extend(mcp_results)

            # Also report persistent hub server state (sse/stdio)
            try:
                hub = get_mcp_hub()
                if hub:
                    rows.extend(hub.health_snapshot())
            except Exception as e:
                rows.append({"tool": "mcp:hub", "ok": False, "detail": str(e)})

        return rows

    def register(
        self,
        name: str,
        func: Callable,
        description: str,
        required_args: list[str] = None,
    ):
        """Register a new tool."""
        tool = Tool(name, func, description, required_args)
        self.tools[name] = tool
        logger.info(f"Registered tool: {name}")

    async def call(self, tool_name: str, **kwargs) -> Any:
        """
        Call a registered tool.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")

        tool = self.tools[tool_name]

        # Validate required args
        for arg in tool.required_args:
            if arg not in kwargs:
                raise ValueError(f"Missing required argument: {arg}")

        logger.info(f"Calling tool: {tool_name} with args: {list(kwargs.keys())}")

        return await tool.call(**kwargs)

    def list_tools(self) -> list[str]:
        """List all available tool names."""
        return list(self.tools.keys())

    def get_tool_schemas(self, allowed: Optional[list[str]] = None) -> list[dict]:
        """
        Return tool definitions in OpenAI function-calling format.
        Pass allowed=[...] to restrict which tools are exposed to the LLM.
        """
        SCHEMAS = {
            "web_search": {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information. Use this for facts, news, or anything requiring up-to-date data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Number of results (default 5)",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            "browser_automation": {
                "type": "function",
                "function": {
                    "name": "browser_automation",
                    "description": "Control a real browser (headless Chromium). Navigate URLs, extract page text, scrape elements, take screenshots, click, or fill forms.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "navigate",
                                    "extract",
                                    "scrape",
                                    "screenshot",
                                    "click",
                                    "fill",
                                ],
                                "description": "Action to perform",
                            },
                            "url": {
                                "type": "string",
                                "description": "URL to open (required for navigate/extract/scrape/screenshot/click/fill)",
                            },
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for extract/scrape/click/fill",
                            },
                            "text": {
                                "type": "string",
                                "description": "Text to type into element (required for fill)",
                            },
                            "screenshot_path": {
                                "type": "string",
                                "description": "Where to save the screenshot",
                            },
                            "wait_for": {
                                "type": "string",
                                "description": "CSS selector to wait for before extracting",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            "file_operations": {
                "type": "function",
                "function": {
                    "name": "file_operations",
                    "description": "Read, write, list, or delete files in the agent workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["read", "write", "list", "delete"],
                                "description": "Operation to perform",
                            },
                            "path": {
                                "type": "string",
                                "description": "File path relative to workspace",
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write (required for write)",
                            },
                        },
                        "required": ["operation"],
                    },
                },
            },
            "code_execution": {
                "type": "function",
                "function": {
                    "name": "code_execution",
                    "description": "Execute code in a secure sandbox and return the output. Supports Python and other languages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The code to execute",
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (default: python)",
                                "default": "python",
                            },
                        },
                        "required": ["code"],
                    },
                },
            },
            "api_call": {
                "type": "function",
                "function": {
                    "name": "api_call",
                    "description": "Make a raw HTTP request to a structured API endpoint that returns JSON or data (e.g. weather APIs, REST APIs, webhooks). Use web_search for general research and browser_automation for human-readable web pages — use this only when you have a specific API URL and need the raw response.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Full URL including https://",
                            },
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                                "default": "GET",
                            },
                            "headers": {
                                "type": "object",
                                "description": "HTTP headers as key-value pairs",
                            },
                            "data": {
                                "type": "object",
                                "description": "JSON body for POST/PUT/PATCH",
                            },
                            "params": {
                                "type": "object",
                                "description": "URL query parameters",
                            },
                        },
                        "required": ["url"],
                    },
                },
            },
            "search_documents": {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": "Search through documents you have uploaded. Use this to find information from PDFs, notes, or any files you have ingested.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What to search for",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of chunks to return (default 5)",
                                "default": 5,
                            },
                            "document_id": {
                                "type": "string",
                                "description": "Restrict search to a specific document ID (optional)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            "github": {
                "type": "function",
                "function": {
                    "name": "github",
                    "description": (
                        "Interact with GitHub. Search repos, read issues and PRs, view file contents, "
                        "list commits, create issues, and add comments. Requires GITHUB_TOKEN."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "search_repos",
                                    "get_repo",
                                    "list_issues",
                                    "get_issue",
                                    "create_issue",
                                    "comment_issue",
                                    "list_prs",
                                    "get_pr",
                                    "get_file",
                                    "list_commits",
                                    "get_user",
                                ],
                                "description": "Action to perform",
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository in owner/repo format (e.g. 'octocat/Hello-World')",
                            },
                            "query": {
                                "type": "string",
                                "description": "Search query (for search_repos)",
                            },
                            "issue_number": {
                                "type": "integer",
                                "description": "Issue number (for get_issue, comment_issue)",
                            },
                            "pr_number": {
                                "type": "integer",
                                "description": "Pull request number (for get_pr)",
                            },
                            "title": {
                                "type": "string",
                                "description": "Issue title (for create_issue)",
                            },
                            "body": {
                                "type": "string",
                                "description": "Issue body or comment text",
                            },
                            "state": {
                                "type": "string",
                                "enum": ["open", "closed", "all"],
                                "description": "Filter issues/PRs by state (default: open)",
                                "default": "open",
                            },
                            "labels": {
                                "type": "string",
                                "description": "Comma-separated label names (for list_issues or create_issue)",
                            },
                            "path": {
                                "type": "string",
                                "description": "File or directory path in the repo (for get_file)",
                            },
                            "branch": {
                                "type": "string",
                                "description": "Branch name (for get_file, list_commits)",
                            },
                            "username": {
                                "type": "string",
                                "description": "GitHub username (for get_user; omit for the authenticated user)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results to return (default 20)",
                                "default": 20,
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
        }

        names = allowed if allowed is not None else list(self.tools.keys())
        schemas: list[dict] = []
        for n in names:
            if n not in self.tools:
                continue
            if n in SCHEMAS:
                schemas.append(SCHEMAS[n])
            elif n in self._dynamic_schemas:
                schemas.append(self._dynamic_schemas[n])
        return schemas

    # ── Precondition registry (sync, no I/O) ─────────────────────────────────
    # Each entry: tool_name → (check_fn, reason_when_missing)
    # check_fn must be a zero-arg callable returning bool.

    @staticmethod
    def _playwright_available() -> bool:
        """Cached check — importlib only, no browser launch."""
        if not hasattr(ToolRegistry, "_playwright_ok"):
            try:
                import importlib
                importlib.import_module("playwright")
                ToolRegistry._playwright_ok = True
            except ImportError:
                ToolRegistry._playwright_ok = False
        return ToolRegistry._playwright_ok  # type: ignore[attr-defined]

    def _precondition_ok(self, name: str) -> tuple[bool, str]:
        """
        Return (ok, reason_string) for a single tool.
        Checks only in-process state — no network I/O.
        """
        checks: dict[str, tuple[bool, str]] = {
            "web_search": (
                bool(settings.SEARXNG_URL or settings.BRAVE_SEARCH_API_KEY),
                "no search provider configured (set SEARXNG_URL or BRAVE_SEARCH_API_KEY)",
            ),
            "browser_automation": (
                self._playwright_available(),
                "Playwright not installed (run: pip install playwright && playwright install chromium)",
            ),
            "code_execution": (
                bool(settings.E2B_API_KEY),
                "E2B_API_KEY not set",
            ),
            "github": (
                bool(settings.GITHUB_TOKEN),
                "GITHUB_TOKEN not set",
            ),
        }
        if name not in checks:
            return True, ""
        ok, reason = checks[name]
        return ok, reason

    # Tools filtered out when the budget is critically low.
    _BUDGET_EXPENSIVE: frozenset[str] = frozenset({"browser_automation", "code_execution"})
    BUDGET_CRITICAL_USD: float = 1.0  # below this → strip expensive tools
    BUDGET_LOW_USD: float = 3.0       # below this → urgent guardrail language

    def get_available_tools_filtered(
        self,
        allowed: Optional[list[str]],
        budget_remaining: float,
    ) -> tuple[list[dict], list[tuple[str, str]]]:
        """
        Return (filtered_schemas, removed_list) where removed_list is
        [(tool_name, reason), ...].

        Filters apply in order:
        1. Precondition checks — sync, no I/O
        2. Budget filter — expensive tools removed below BUDGET_CRITICAL_USD
        """
        all_schemas = self.get_tool_schemas(allowed)
        filtered: list[dict] = []
        removed: list[tuple[str, str]] = []

        for schema in all_schemas:
            name = schema.get("function", {}).get("name", "")

            ok, reason = self._precondition_ok(name)
            if not ok:
                removed.append((name, f"precondition: {reason}"))
                logger.debug("Tool %s filtered — %s", name, reason)
                continue

            if budget_remaining < self.BUDGET_CRITICAL_USD and name in self._BUDGET_EXPENSIVE:
                removed.append((name, f"budget_critical (${budget_remaining:.2f} remaining)"))
                logger.info("Tool %s filtered — budget critical (${%.2f})", name, budget_remaining)
                continue

            filtered.append(schema)

        return filtered, removed

    def get_tool_info(self, tool_name: str) -> dict:
        """Get information about a tool."""
        if tool_name not in self.tools:
            return {}

        tool = self.tools[tool_name]
        return {
            "name": tool.name,
            "description": tool.description,
            "required_args": tool.required_args,
        }

    # ========================================================================
    # Built-in Tool Implementations (Placeholders)
    # ========================================================================

    async def _web_search(self, query: str, max_results: int = 5) -> dict:
        """
        Search the web. Tries SearXNG first, falls back to Brave Search if unreachable.
        """
        result = await self._searxng_search(query, max_results)
        if result.get("results"):
            return result

        logger.warning("SearXNG returned no results — trying Brave Search fallback")
        return await self._brave_search(query, max_results)

    async def _searxng_search(self, query: str, max_results: int = 5) -> dict:
        """Search via SearXNG (primary)."""
        logger.info(f"SearXNG search: {query}")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{settings.SEARXNG_URL}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "categories": "general",
                        "language": "en",
                    },
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "source": f"searxng:{r.get('engine', '')}",
                }
                for r in data.get("results", [])[:max_results]
            ]
            return {
                "query": query,
                "results": results,
                "total": len(results),
                "provider": "searxng",
            }

        except httpx.ConnectError:
            logger.error(f"SearXNG unreachable at {settings.SEARXNG_URL}")
            return {"query": query, "results": [], "error": "searxng_unreachable"}
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            return {"query": query, "results": [], "error": str(e)}

    async def _brave_search(self, query: str, max_results: int = 5) -> dict:
        """Search via Brave Search API (fallback)."""
        if not settings.BRAVE_SEARCH_API_KEY:
            logger.error(
                "Brave Search fallback unavailable — BRAVE_SEARCH_API_KEY not set"
            )
            return {
                "query": query,
                "results": [],
                "error": "no_search_provider_available",
            }

        logger.info(f"Brave Search fallback: {query}")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results},
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                    "source": "brave",
                }
                for r in data.get("web", {}).get("results", [])[:max_results]
            ]
            return {
                "query": query,
                "results": results,
                "total": len(results),
                "provider": "brave",
            }

        except Exception as e:
            logger.error(f"Brave Search failed: {e}")
            return {"query": query, "results": [], "error": str(e)}

    async def _browser_automation(
        self,
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
        screenshot_path: str = "",
        wait_for: str = "",
        timeout: int = 15000,
    ) -> str:
        """
        Automate browser tasks using Playwright (headless Chromium).

        Actions:
          navigate    — load a URL, return page title + visible text
          extract     — return text content of elements matching a CSS selector
          screenshot  — save a screenshot to a path and return the path
          click       — click an element matching a CSS selector
          fill        — fill an input matching a CSS selector with text
          scrape      — navigate + extract in one call (selector required)
        """
        logger.info(f"Browser automation: {action} {url}")

        if url:
            ok, reason = validate_agent_outbound_url(url)
            if not ok:
                return f"Error: URL not allowed ({reason})"
            parsed = urlparse(url)
            if parsed.hostname:
                ok_host, msg_host = validate_browser_automation_host(
                    parsed.hostname,
                    settings.BROWSER_AUTOMATION_ALLOWED_HOST_SUFFIXES,
                )
                if not ok_host:
                    return f"Error: URL not allowed ({msg_host})"

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return (
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    if action in (
                        "navigate",
                        "extract",
                        "scrape",
                        "screenshot",
                        "click",
                        "fill",
                    ):
                        if not url:
                            return "Error: url is required"
                        await page.goto(
                            url, timeout=timeout, wait_until="domcontentloaded"
                        )
                        if wait_for:
                            await page.wait_for_selector(wait_for, timeout=timeout)

                    if action == "navigate":
                        title = await page.title()
                        # Get readable text — strip scripts/styles
                        body_text = await page.evaluate("""() => {
                            const clone = document.body.cloneNode(true);
                            clone.querySelectorAll('script,style,nav,footer,header').forEach(e => e.remove());
                            return clone.innerText.replace(/\\s+/g, ' ').trim();
                        }""")
                        return f"Title: {title}\n\n{truncate_head(body_text)}"

                    elif action in ("extract", "scrape"):
                        if not selector:
                            return "Error: selector is required for extract/scrape"
                        elements = await page.query_selector_all(selector)
                        texts = []
                        for el in elements[:20]:
                            t = await el.inner_text()
                            if t.strip():
                                texts.append(t.strip())
                        return (
                            "\n---\n".join(texts)
                            if texts
                            else "No elements matched selector"
                        )

                    elif action == "screenshot":
                        ws_root = (
                            Path(settings.AGENT_WORKSPACE_DIR).expanduser().resolve()
                        )
                        ws_root.mkdir(parents=True, exist_ok=True)
                        if screenshot_path:
                            try:
                                candidate = (
                                    ws_root / Path(screenshot_path).name
                                ).resolve()
                                candidate.relative_to(ws_root)
                            except ValueError:
                                return "Error: screenshot path must be inside the workspace"
                            safe_ss_path = str(candidate)
                        else:
                            safe_ss_path = str(ws_root / "screenshot.png")
                        await page.screenshot(path=safe_ss_path, full_page=True)
                        return f"Screenshot saved to {safe_ss_path}"

                    elif action == "click":
                        if not selector:
                            return "Error: selector is required for click"
                        await page.click(selector, timeout=timeout)
                        return f"Clicked: {selector}"

                    elif action == "fill":
                        if not selector or not text:
                            return "Error: selector and text are required for fill"
                        await page.fill(selector, text)
                        return f"Filled '{selector}' with text"

                    else:
                        return f"Unknown action: {action}. Use navigate, extract, scrape, screenshot, click, or fill."

                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"Browser automation failed: {e}")
            return f"Browser automation error: {e}"

    async def _file_operations(
        self,
        operation: str,
        path: str = "",
        content: str = "",
        workspace: str = settings.AGENT_WORKSPACE_DIR,
    ) -> str:
        """Read/write files within a sandboxed workspace directory."""
        import aiofiles

        logger.info(f"File operation: {operation} on {path}")

        # Restrict to workspace — prevent path traversal (including /ws_evil vs /ws prefix bypass)
        ws_root = Path(workspace).expanduser().resolve()
        try:
            candidate = (ws_root / path.lstrip("/")).resolve()
        except (OSError, RuntimeError):
            return "Error: invalid path"
        try:
            candidate.relative_to(ws_root)
        except ValueError:
            return "Error: path traversal not allowed"
        safe_path = str(candidate)

        os.makedirs(workspace, exist_ok=True)

        if operation == "read":
            try:
                async with aiofiles.open(safe_path, "r") as f:
                    text = await f.read()
                return truncate_head(text)
            except FileNotFoundError:
                return f"Error: file not found: {path}"
            except Exception as e:
                return f"Error reading file: {e}"

        elif operation == "write":
            try:
                os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                async with aiofiles.open(safe_path, "w") as f:
                    await f.write(content)
                return f"Written {len(content)} bytes to {path}"
            except Exception as e:
                return f"Error writing file: {e}"

        elif operation == "list":
            try:
                list_dir = safe_path if os.path.isdir(safe_path) else str(ws_root)
                entries = os.listdir(list_dir)
                return "\n".join(entries)
            except Exception as e:
                return f"Error listing directory: {e}"

        elif operation == "delete":
            try:
                os.remove(safe_path)
                return f"Deleted: {path}"
            except Exception as e:
                return f"Error deleting file: {e}"

        else:
            return f"Unknown operation: {operation}. Use read, write, list, or delete."

    async def _code_execution(self, code: str, language: str = "python") -> str:
        """
        Execute code in a sandboxed environment.
        Requires E2B_API_KEY to be set. Returns placeholder if not configured.
        """
        logger.info(f"Code execution: {language}")

        if not settings.E2B_API_KEY:
            return (
                f"Code execution not available — E2B_API_KEY not set.\n"
                f"To enable: add E2B_API_KEY to your .env\n\n"
                f"Code received ({language}):\n{code}"
            )

        # E2B code interpreter (optional dependency). Official pattern: async context manager.
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            return "Code execution not available — install e2b-code-interpreter package"

        try:
            async with Sandbox() as sbx:
                result = sbx.run_code(code)
            output = "\n".join(str(r) for r in result.results)
            if result.error:
                output += f"\nError: {result.error}"
            return output or "(no output)"
        except Exception as e:
            return f"Code execution failed: {e}"

    async def _api_call(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: float = 15.0,
    ) -> dict:
        """Make HTTP requests to external APIs."""
        logger.info(f"API call: {method} {url}")

        # Basic URL validation — must be http/https
        if not url.startswith(("http://", "https://")):
            return {"error": "URL must start with http:// or https://"}
        ok, reason = validate_agent_outbound_url(url)
        if not ok:
            return {"error": f"URL not allowed: {reason}"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers or {},
                    json=data if method.upper() in ("POST", "PUT", "PATCH") else None,
                    params=params,
                )
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:2000]

                return {
                    "status": resp.status_code,
                    "headers": redact_response_headers(dict(resp.headers)),
                    "data": body,
                }
        except httpx.TimeoutException:
            return {"error": f"Request timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    async def _search_documents(
        self,
        query: str,
        limit: int = 5,
        document_id: Optional[str] = None,
    ) -> str:
        """Search ingested documents for relevant content."""
        from app.agent.documents import search_documents

        results = await search_documents(query, limit=limit, document_id=document_id)
        if not results:
            return "No relevant content found in your documents for that query."
        lines = []
        for r in results:
            lines.append(
                f"[{r['filename']} — chunk {r['chunk_index']}]\n{r['content']}"
            )
        return "\n\n---\n\n".join(lines)

    async def _github(
        self,
        action: str,
        repo: str = "",
        query: str = "",
        issue_number: int = 0,
        pr_number: int = 0,
        title: str = "",
        body: str = "",
        state: str = "open",
        labels: str = "",
        path: str = "",
        branch: str = "",
        username: str = "",
        limit: int = 20,
    ) -> Any:
        """GitHub connector — delegates to the connector module."""
        from app.tools.connectors.github import github_action
        from app.utils.settings_store import load_settings_dict

        cfg = load_settings_dict().get("connectors", {}).get("github", {})
        if cfg.get("enabled") is False and not settings.GITHUB_TOKEN:
            return {
                "error": "GitHub connector is disabled. Enable it in Connectors settings."
            }
        # Stored token takes priority over env var so the UI can override without a restart.
        token = cfg.get("token") or settings.GITHUB_TOKEN

        return await github_action(
            action,
            token,
            repo=repo,
            query=query,
            issue_number=issue_number,
            pr_number=pr_number,
            title=title,
            body=body,
            state=state,
            labels=labels,
            path=path,
            branch=branch,
            username=username,
            limit=limit,
        )
