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
            description="Search the web. Call multiple times with different queries for thorough research. Supports pagination via page=2/3.",
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

        # Skill management — agent-writable skill chains
        self.register(
            name="skill_manage",
            func=self._skill_manage,
            description=(
                "Create, update, delete, list, or search your own skill chains. "
                "After solving a novel or complex task, save the approach as a skill "
                "so future similar tasks benefit from what you learned."
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

        browser_ok = self._playwright_available()
        rows.append(
            {
                "tool": "browser_automation",
                "ok": browser_ok,
                "detail": (
                    "chromium_binary_found"
                    if browser_ok
                    else "run: playwright install chromium"
                ),
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
                    "description": (
                        "Search the web for current information. "
                        "For thorough research: call this 2-4 times with different query angles "
                        "(e.g. broad overview first, then specific subtopics). "
                        "Use page=2 or page=3 to get more results beyond the first batch. "
                        "Use max_results=10 or higher for comprehensive coverage."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Number of results to return (default 10, max 20)",
                                "default": 10,
                            },
                            "page": {
                                "type": "integer",
                                "description": "Result page number for pagination — use 2 or 3 to get additional results beyond the first batch (default 1)",
                                "default": 1,
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
            "skill_manage": {
                "type": "function",
                "function": {
                    "name": "skill_manage",
                    "description": (
                        "Manage your skill chain library. Use 'create' after solving a novel task "
                        "to save the approach for reuse. Use 'list' or 'search' to find existing "
                        "chains. Use 'update' to refine steps. Use 'delete' to remove outdated chains."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "create",
                                    "update",
                                    "delete",
                                    "list",
                                    "search",
                                ],
                                "description": "Operation: create new chain, update existing, delete, list all, or search by task_type",
                            },
                            "name": {
                                "type": "string",
                                "description": "Unique chain name (required for create; snake_case recommended)",
                            },
                            "task_type": {
                                "type": "string",
                                "description": "Task category: coding, research, writing, analysis, data, planning, automation, general",
                            },
                            "steps": {
                                "type": "array",
                                "description": "Ordered tool steps. Each item: {tool: str, description: str, hint?: str}",
                                "items": {"type": "object"},
                            },
                            "description": {
                                "type": "string",
                                "description": "Human-readable summary of when to use this chain",
                            },
                            "trigger_keywords": {
                                "type": "array",
                                "description": "Extra keywords that activate this chain (beyond task_type matching)",
                                "items": {"type": "string"},
                            },
                            "chain_id": {
                                "type": "string",
                                "description": "Chain UUID — required for update and delete",
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
        """Check that playwright package is installed AND a chromium binary directory exists.

        Not cached — the filesystem glob is cheap and this way the check stays
        accurate after ``playwright install`` without requiring a server restart.
        """
        try:
            import importlib
            import platform

            importlib.import_module("playwright")
            system = platform.system()
            if system == "Darwin":
                base = Path.home() / "Library" / "Caches" / "ms-playwright"
            elif system == "Windows":
                base = Path.home() / "AppData" / "Local" / "ms-playwright"
            else:
                base = Path.home() / ".cache" / "ms-playwright"
            return base.exists() and bool(list(base.glob("chromium*")))
        except Exception:
            return False

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
    _BUDGET_EXPENSIVE: frozenset[str] = frozenset(
        {"browser_automation", "code_execution"}
    )
    BUDGET_CRITICAL_USD: float = 1.0  # below this → strip expensive tools
    BUDGET_LOW_USD: float = 3.0  # below this → urgent guardrail language

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

            if (
                budget_remaining < self.BUDGET_CRITICAL_USD
                and name in self._BUDGET_EXPENSIVE
            ):
                removed.append(
                    (name, f"budget_critical (${budget_remaining:.2f} remaining)")
                )
                logger.info(
                    "Tool %s filtered — budget critical (${%.2f})",
                    name,
                    budget_remaining,
                )
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

    async def _web_search(
        self, query: str, max_results: int = 10, page: int = 1
    ) -> dict:
        """
        Search the web. Tries SearXNG first, falls back to Brave Search if unreachable.
        """
        max_results = min(max(1, max_results), 20)  # clamp 1–20
        page = max(1, page)
        result = await self._searxng_search(query, max_results, page)
        if result.get("results"):
            return result

        logger.warning("SearXNG returned no results — trying Brave Search fallback")
        return await self._brave_search(query, max_results, page)

    async def _searxng_search(
        self, query: str, max_results: int = 10, page: int = 1
    ) -> dict:
        """Search via SearXNG (primary)."""
        logger.info(f"SearXNG search: {query} (max={max_results}, page={page})")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{settings.SEARXNG_URL}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "categories": "general",
                        "language": "en",
                        "pageno": page,
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
                "page": page,
            }

        except httpx.ConnectError:
            logger.error(f"SearXNG unreachable at {settings.SEARXNG_URL}")
            return {"query": query, "results": [], "error": "searxng_unreachable"}
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            return {"query": query, "results": [], "error": str(e)}

    async def _brave_search(
        self, query: str, max_results: int = 10, page: int = 1
    ) -> dict:
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

        offset = (page - 1) * max_results
        logger.info(f"Brave Search: {query} (count={max_results}, offset={offset})")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results, "offset": offset},
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
                "page": page,
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
        Execute code in an E2B cloud sandbox and return the output.
        Requires E2B_API_KEY. Supports Python by default; pass language= for others.
        """
        logger.info(f"Code execution: {language}")

        if not settings.E2B_API_KEY:
            return (
                f"Code execution not available — E2B_API_KEY not set.\n"
                f"To enable: add E2B_API_KEY to your .env\n\n"
                f"Code received ({language}):\n{code}"
            )

        try:
            from e2b_code_interpreter import AsyncSandbox
        except ImportError:
            return "Code execution not available — install e2b-code-interpreter package"

        try:
            sbx = await AsyncSandbox.create(
                api_key=settings.E2B_API_KEY,
                timeout=120,  # sandbox lifetime in seconds
            )
            async with sbx:
                execution = await sbx.run_code(
                    code,
                    language=language if language != "python" else None,
                    timeout=60,  # per-run execution timeout
                )

            parts: list[str] = []

            # stdout — print() output and other writes to stdout
            if execution.logs and execution.logs.stdout:
                parts.append("".join(execution.logs.stdout).rstrip())

            # rich results — return values, reprs, display() output
            for result in execution.results or []:
                text = (result.text or "").strip()
                if text:
                    parts.append(text)

            # stderr — warnings, deprecation notices, etc.
            if execution.logs and execution.logs.stderr:
                stderr_text = "".join(execution.logs.stderr).rstrip()
                if stderr_text:
                    parts.append(f"stderr:\n{stderr_text}")

            # execution error — exception name, message, traceback
            if execution.error:
                parts.append(f"{execution.error.name}: {execution.error.value}")
                if execution.error.traceback:
                    parts.append(execution.error.traceback.rstrip())

            return "\n\n".join(parts) if parts else "(no output)"

        except Exception as e:
            logger.error(f"Code execution failed: {e}")
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
        """Make HTTP requests to external APIs.

        Connects to the pre-resolved IP address to prevent DNS rebinding attacks.
        For HTTPS the original hostname is used for both TLS SNI and cert verification
        via httpcore's sni_hostname extension, so certificate validation is unaffected.
        """
        import asyncio as _asyncio
        import ipaddress as _ipaddress
        import json as _json
        import socket as _socket
        import ssl as _ssl
        import httpcore

        logger.info(f"API call: {method} {url}")

        if not url.startswith(("http://", "https://")):
            return {"error": "URL must start with http:// or https://"}
        ok, reason = validate_agent_outbound_url(url)
        if not ok:
            return {"error": f"URL not allowed: {reason}"}

        parsed = urlparse(url)
        host = parsed.hostname or ""
        scheme = parsed.scheme
        default_port = 443 if scheme == "https" else 80
        port = parsed.port or default_port

        # ── Pre-resolve DNS so the TCP connection uses the validated IP directly.
        # This closes the window between SSRF validation and the actual connection
        # (DNS rebinding: a TTL-0 response could flip to a private IP between calls).
        try:
            loop = _asyncio.get_event_loop()
            infos = await loop.getaddrinfo(host, port, type=_socket.SOCK_STREAM)
            if not infos:
                return {"error": f"Could not resolve host: {host}"}
            resolved_ip = infos[0][4][0]
            ip_obj = _ipaddress.ip_address(resolved_ip)
            if not ip_obj.is_global:
                return {
                    "error": f"Host resolved to non-public IP at connection time: {resolved_ip}"
                }
        except (OSError, ValueError) as e:
            return {"error": f"DNS resolution failed: {e}"}

        # Build URL target path (including query string and any extra params)
        target = parsed.path or "/"
        query = parsed.query or ""
        if params:
            from urllib.parse import urlencode

            extra = urlencode(params)
            query = f"{query}&{extra}" if query else extra
        if query:
            target = f"{target}?{query}"

        # Build request headers — Host must reflect the original hostname for HTTP/1.1
        req_headers: list[tuple[bytes, bytes]] = [
            (b"host", host.encode()),
            (b"user-agent", b"agent/1.0"),
            (b"accept", b"application/json, */*"),
        ]
        for k, v in (headers or {}).items():
            req_headers.append(
                (
                    k.encode() if isinstance(k, str) else k,
                    v.encode() if isinstance(v, str) else v,
                )
            )

        body_bytes = b""
        if method.upper() in ("POST", "PUT", "PATCH") and data is not None:
            body_bytes = _json.dumps(data).encode()
            req_headers.append((b"content-type", b"application/json"))
            req_headers.append((b"content-length", str(len(body_bytes)).encode()))

        # ── Connect to the pre-resolved IP.
        # For HTTPS: sni_hostname tells httpcore/ssl to use the original hostname
        # for TLS SNI negotiation and certificate verification.
        extensions: dict = {}
        ssl_context = None
        if scheme == "https":
            ssl_context = _ssl.create_default_context()
            extensions["sni_hostname"] = host.encode()

        try:
            async with httpcore.AsyncConnectionPool(
                ssl_context=ssl_context,
                keepalive_expiry=timeout,
            ) as pool:
                response = await _asyncio.wait_for(
                    pool.request(
                        method=method.upper().encode(),
                        url=httpcore.URL(
                            scheme=scheme.encode(),
                            host=resolved_ip.encode(),
                            port=port,
                            target=target.encode(),
                        ),
                        headers=req_headers,
                        content=body_bytes,
                        extensions=extensions,
                    ),
                    timeout=timeout,
                )
                raw_body = await response.aread()

            try:
                body: Any = _json.loads(raw_body)
            except Exception:
                body = raw_body.decode("utf-8", errors="replace")[:2000]

            resp_headers = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in response.headers.raw_items()
            }
            return {
                "status": response.status,
                "headers": redact_response_headers(resp_headers),
                "data": body,
            }
        except _asyncio.TimeoutError:
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

    async def _skill_manage(
        self,
        action: str,
        name: str = "",
        task_type: str = "general",
        steps: Optional[list] = None,
        description: str = "",
        trigger_keywords: Optional[list] = None,
        chain_id: str = "",
    ) -> dict:
        """Agent-callable skill chain management."""
        from app.agent.skill_composer import (
            list_chains,
            create_chain,
            update_chain,
            delete_chain,
            get_applicable_chain,
        )

        action = (action or "").strip().lower()

        if action == "list":
            chains = await list_chains()
            if not chains:
                return {"chains": [], "message": "No skill chains defined yet."}
            summary = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "task_type": c["task_type"],
                    "steps": [s.get("tool") for s in (c.get("steps") or [])],
                    "success_rate": c["success_rate"],
                    "total_runs": c["total_runs"],
                }
                for c in chains
            ]
            return {"chains": summary, "count": len(chains)}

        if action == "search":
            chain = await get_applicable_chain(task_type or name or "general")
            if not chain:
                return {
                    "found": False,
                    "message": f"No chain found for task_type='{task_type}'",
                }
            return {"found": True, "chain": chain}

        if action == "create":
            if not name:
                return {"error": "name is required for create"}
            if not steps:
                return {"error": "steps list is required for create"}
            step_objs = []
            for s in steps:
                if isinstance(s, str):
                    step_objs.append({"tool": s, "description": ""})
                elif isinstance(s, dict):
                    step_objs.append(s)
            try:
                chain = await create_chain(
                    name=name.strip(),
                    task_type=task_type or "general",
                    steps=step_objs,
                    description=description,
                    trigger_keywords=trigger_keywords or [],
                )
                return {
                    "created": True,
                    "chain": chain,
                    "message": f"Skill chain '{name}' saved.",
                }
            except Exception as e:
                return {"error": str(e)}

        if action == "update":
            if not chain_id:
                return {"error": "chain_id is required for update"}
            step_objs = None
            if steps is not None:
                step_objs = [
                    {"tool": s, "description": ""} if isinstance(s, str) else s
                    for s in steps
                ]
            updated = await update_chain(
                chain_id,
                steps=step_objs,
                description=description or None,
                trigger_keywords=trigger_keywords,
            )
            if not updated:
                return {"error": f"Chain {chain_id} not found"}
            return {"updated": True, "chain": updated}

        if action == "delete":
            if not chain_id:
                return {"error": "chain_id is required for delete"}
            deleted = await delete_chain(chain_id)
            if not deleted:
                return {"error": f"Chain {chain_id} not found"}
            return {"deleted": True, "chain_id": chain_id}

        return {
            "error": f"Unknown action '{action}'. Use: create, update, delete, list, search"
        }
