"""
Tool Registry - Manages all available tools the agent can use.
"""

import logging
import os
import httpx
from typing import Any, Callable, Dict, Optional
from inspect import signature

from app.config import settings
from app.utils.truncate import truncate_head

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
        
        # Code Execution — only register when E2B sandbox is configured.
        # Without E2B_API_KEY the tool always fails, adding noise to the schema.
        if settings.E2B_API_KEY:
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
                            "query": {"type": "string", "description": "The search query"},
                            "max_results": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
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
                                "enum": ["navigate", "extract", "scrape", "screenshot", "click", "fill"],
                                "description": "Action to perform",
                            },
                            "url": {"type": "string", "description": "URL to open (required for navigate/extract/scrape/screenshot/click/fill)"},
                            "selector": {"type": "string", "description": "CSS selector for extract/scrape/click/fill"},
                            "text": {"type": "string", "description": "Text to type into element (required for fill)"},
                            "screenshot_path": {"type": "string", "description": "Where to save the screenshot"},
                            "wait_for": {"type": "string", "description": "CSS selector to wait for before extracting"},
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
                            "path": {"type": "string", "description": "File path relative to workspace"},
                            "content": {"type": "string", "description": "Content to write (required for write)"},
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
                            "code": {"type": "string", "description": "The code to execute"},
                            "language": {"type": "string", "description": "Programming language (default: python)", "default": "python"},
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
                            "url": {"type": "string", "description": "Full URL including https://"},
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
                            "headers": {"type": "object", "description": "HTTP headers as key-value pairs"},
                            "data": {"type": "object", "description": "JSON body for POST/PUT/PATCH"},
                            "params": {"type": "object", "description": "URL query parameters"},
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
                            "query": {"type": "string", "description": "What to search for"},
                            "limit": {"type": "integer", "description": "Number of chunks to return (default 5)", "default": 5},
                            "document_id": {"type": "string", "description": "Restrict search to a specific document ID (optional)"},
                        },
                        "required": ["query"],
                    },
                },
            },
        }

        names = allowed if allowed is not None else list(self.tools.keys())
        return [SCHEMAS[n] for n in names if n in SCHEMAS and n in self.tools]

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
            return {"query": query, "results": results, "total": len(results), "provider": "searxng"}

        except httpx.ConnectError:
            logger.error(f"SearXNG unreachable at {settings.SEARXNG_URL}")
            return {"query": query, "results": [], "error": "searxng_unreachable"}
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            return {"query": query, "results": [], "error": str(e)}

    async def _brave_search(self, query: str, max_results: int = 5) -> dict:
        """Search via Brave Search API (fallback)."""
        if not settings.BRAVE_SEARCH_API_KEY:
            logger.error("Brave Search fallback unavailable — BRAVE_SEARCH_API_KEY not set")
            return {"query": query, "results": [], "error": "no_search_provider_available"}

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
            return {"query": query, "results": results, "total": len(results), "provider": "brave"}

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
                    if action in ("navigate", "extract", "scrape", "screenshot", "click", "fill"):
                        if not url:
                            return "Error: url is required"
                        await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
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
                        return "\n---\n".join(texts) if texts else "No elements matched selector"

                    elif action == "screenshot":
                        path = screenshot_path or os.path.join(settings.AGENT_WORKSPACE_DIR, "screenshot.png")
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        await page.screenshot(path=path, full_page=True)
                        return f"Screenshot saved to {path}"

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

        # Restrict to workspace — prevent path traversal
        safe_path = os.path.realpath(os.path.join(workspace, path.lstrip("/")))
        if not safe_path.startswith(os.path.realpath(workspace)):
            return "Error: path traversal not allowed"

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
                entries = os.listdir(safe_path if os.path.isdir(safe_path) else workspace)
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

        # E2B sandbox execution (requires e2b package)
        try:
            from e2b_code_interpreter import Sandbox
            async with Sandbox() as sbx:
                result = sbx.run_code(code)
                output = "\n".join(str(r) for r in result.results)
                if result.error:
                    output += f"\nError: {result.error}"
                return output or "(no output)"
        except ImportError:
            return "Code execution not available — install e2b-code-interpreter package"
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
                    "headers": dict(resp.headers),
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
            lines.append(f"[{r['filename']} — chunk {r['chunk_index']}]\n{r['content']}")
        return "\n\n---\n\n".join(lines)
