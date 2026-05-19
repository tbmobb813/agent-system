"""
AI Agent TUI — full terminal interface built with Textual.

Usage:
    python -m cli
    # or after pip install: agent

Key bindings:
    Enter          Submit message
    Shift+Enter    Insert newline (multiline messages)
    Ctrl+Enter     Submit message (alternative)
    Ctrl+C         Stop current run / exit if idle
    Ctrl+L         Clear output
    Ctrl+R         Retry last message
    Ctrl+Up / Ctrl+Down  Cycle input history (when input is focused)
    Tab            Autocomplete slash command

Slash commands:
    /new           Start fresh conversation
    /stop          Stop current run
    /retry         Resend last message
    /history       Show recent tasks
    /skills        Show learned skills
    /memory <q>    Search memories
    /usage         Show cost & budget
    /clear         Clear output
    /help          List commands
    /exit          Quit
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, RichLog, Static, TextArea
from textual.worker import Worker, WorkerState

from cli import client

# ── Constants ─────────────────────────────────────────────────────────────────

SLASH_COMMANDS: list[str] = [
    "/new", "/stop", "/retry", "/history", "/skills",
    "/memory", "/usage", "/clear", "/help", "/exit",
]

HELP_TEXT = """\
[bold cyan]Slash commands[/]
  [cyan]/new[/]            Start a fresh conversation
  [cyan]/stop[/]           Stop the current run
  [cyan]/retry[/]          Resend your last message
  [cyan]/history[/]        Show recent tasks
  [cyan]/skills[/]         Show learned skill profile
  [cyan]/memory[/] [dim]<query>[/]  Search memories
  [cyan]/usage[/]          Show cost & budget status
  [cyan]/clear[/]          Clear the output panel
  [cyan]/help[/]           Show this message
  [cyan]/exit[/]           Quit

[bold cyan]Key bindings[/]
  [cyan]Enter[/]           Submit
  [cyan]Shift+Enter[/]     Insert newline
  [cyan]Ctrl+C[/]          Stop run / exit
  [cyan]Ctrl+L[/]          Clear output
  [cyan]Ctrl+R[/]          Retry last message
  [cyan]Ctrl+Up / Ctrl+Down[/]  Cycle input history\
"""


# ── Input widget ──────────────────────────────────────────────────────────────

class AgentInput(TextArea):
    """
    Multiline input with submit-on-Enter.

    - Enter → submit and clear
    - Shift+Enter → insert newline (natural TextArea behaviour)
    - Ctrl+Enter → also submit (for terminals that distinguish it)
    - Tab → cycle slash-command autocomplete when line starts with /
    - Up/Down (when content is single-line and cursor at start/end) → input history
    """

    class Submit(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.value = text

    # Input history
    _history: ClassVar[list[str]] = []
    _history_idx: int = -1

    def on_key(self, event) -> None:  # noqa: ANN001
        key = event.key

        if key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.rstrip("\n")
            if text.strip():
                AgentInput._history.append(text)
                AgentInput._history_idx = -1
                self.post_message(self.Submit(text))
                self.load_text("")
            return

        if key == "ctrl+enter":
            event.prevent_default()
            event.stop()
            text = self.text.rstrip("\n")
            if text.strip():
                AgentInput._history.append(text)
                AgentInput._history_idx = -1
                self.post_message(self.Submit(text))
                self.load_text("")
            return

        if key == "tab":
            line = self.text
            if line.startswith("/"):
                matches = [c for c in SLASH_COMMANDS if c.startswith(line.rstrip())]
                if len(matches) == 1:
                    event.prevent_default()
                    event.stop()
                    self.load_text(matches[0] + " ")
                    self.move_cursor(self.get_cursor_line_end_location())
                elif matches:
                    event.prevent_default()
                    event.stop()
                    # Cycle through matches
                    current = line.rstrip()
                    try:
                        idx = (matches.index(current) + 1) % len(matches)
                    except ValueError:
                        idx = 0
                    self.load_text(matches[idx] + " ")
                    self.move_cursor(self.get_cursor_line_end_location())
            return

        if key == "ctrl+up":
            event.prevent_default()
            event.stop()
            hist = AgentInput._history
            if not hist:
                return
            AgentInput._history_idx = min(
                AgentInput._history_idx + 1, len(hist) - 1
            )
            self.load_text(hist[-(AgentInput._history_idx + 1)])
            self.move_cursor(self.get_cursor_line_end_location())
            return

        if key == "ctrl+down":
            event.prevent_default()
            event.stop()
            hist = AgentInput._history
            AgentInput._history_idx -= 1
            if AgentInput._history_idx < 0:
                AgentInput._history_idx = -1
                self.load_text("")
            else:
                self.load_text(hist[-(AgentInput._history_idx + 1)])
                self.move_cursor(self.get_cursor_line_end_location())
            return


# ── App ───────────────────────────────────────────────────────────────────────

class AgentApp(App[None]):
    CSS = """
    Screen {
        background: #0d1117;
        layers: base overlay;
    }

    #header {
        height: 1;
        background: #161b22;
        color: #58a6ff;
        padding: 0 1;
        layer: base;
    }

    #output {
        height: 1fr;
        background: #0d1117;
        border: none;
        padding: 0 1;
        scrollbar-color: #30363d #0d1117;
        layer: base;
    }

    #status-bar {
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
        layer: base;
    }

    #prompt-row {
        height: 1;
        background: #0d1117;
        padding: 0 1;
        layer: base;
    }

    AgentInput {
        height: auto;
        min-height: 1;
        max-height: 8;
        background: #0d1117;
        color: #e6edf3;
        border: none;
        padding: 0 3;
        layer: base;
    }

    AgentInput:focus {
        border: none;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
        layer: base;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Stop / Exit", priority=True, show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
        Binding("ctrl+r", "retry", "Retry", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._conversation_id: str | None = None
        self._task_id: str | None = None
        self._streaming = False
        self._last_query: str | None = None
        self._stream_worker: Worker | None = None
        self._spent: float = 0.0
        self._last_model: str = "auto"

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield RichLog(id="output", highlight=True, markup=True, wrap=True)
        yield Static("", id="status-bar")
        yield Static("[bold cyan]>[/] ", id="prompt-row")
        yield AgentInput("", language=None, id="agent-input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(AgentInput).focus()
        output = self.query_one(RichLog)
        output.write(
            "[bold]AI AGENT CLI[/]  —  type a message or [cyan]/help[/] for commands\n"
        )
        for err in client.config_errors():
            output.write(f"[yellow]⚠ {err}[/]")
        self._refresh_header()

    # ── Header ────────────────────────────────────────────────────────────────

    def _header_text(self) -> str:
        conv = f"conv:{self._conversation_id[:8]}…" if self._conversation_id else "no conversation"
        model = self._last_model
        cost = f"${self._spent:.4f}"
        return f" AI AGENT  ·  {conv}  ·  {model}  ·  {cost}"

    def _refresh_header(self) -> None:
        self.query_one("#header", Static).update(self._header_text())

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    # ── Submit ────────────────────────────────────────────────────────────────

    def on_agent_input_submit(self, message: AgentInput.Submit) -> None:
        text = message.value.strip()
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._run_query(text)

    def _run_query(self, query: str) -> None:
        if self._streaming:
            self._print("[yellow]⚠ Already running — /stop to cancel[/]")
            return
        self._last_query = query
        output = self.query_one(RichLog)
        ts = datetime.now().strftime("%H:%M")
        output.write(f"\n[bold white][{ts}] you:[/] {query}")
        self._stream_worker = self._do_stream(query)

    # ── SSE streaming worker ──────────────────────────────────────────────────

    @work(exclusive=False, thread=False)
    async def _do_stream(self, query: str) -> None:
        self._streaming = True
        self._task_id = None
        output = self.query_one(RichLog)
        status = self.query_one("#status-bar", Static)
        accumulated: list[str] = []

        try:
            status.update("[dim cyan]◌ connecting…[/]")
            async for event in client.stream_agent(query, self._conversation_id):
                etype = event.get("type", "")

                # Capture task_id from the first events that carry it
                if not self._task_id and event.get("task_id"):
                    self._task_id = str(event["task_id"])

                # Capture conversation_id whenever it arrives
                if event.get("conversation_id"):
                    self._conversation_id = str(event["conversation_id"])
                    self._refresh_header()

                if etype == "status":
                    content = event.get("content") or event.get("message", "")
                    if content:
                        status.update(f"[dim cyan]◌ {content}[/]")

                elif etype == "thinking":
                    content = event.get("content", "")
                    if content:
                        output.write(f"[dim]💭 {content[:300]}[/]")

                elif etype == "tool_call":
                    name = event.get("tool_name", "?")
                    inp = event.get("tool_input") or {}
                    preview = str(inp)[:120].replace("\n", " ")
                    output.write(f"[yellow]⚙  {name}[/] [dim]{preview}[/]")
                    status.update(f"[dim yellow]⚙ running {name}…[/]")

                elif etype == "tool_result":
                    name = event.get("tool_name", "?")
                    result = str(event.get("tool_result", ""))
                    preview = result[:200].replace("\n", " ")
                    output.write(f"[dim]   └─ {name}: {preview}[/]")

                elif etype == "text_delta":
                    chunk = event.get("content", "")
                    if chunk:
                        accumulated.append(chunk)
                        # capture model name if present
                        if event.get("model") and event["model"] != "unknown":
                            self._last_model = event["model"].split("/")[-1]

                elif etype == "done":
                    cost = float(event.get("cost") or 0)
                    self._spent += cost
                    if accumulated:
                        output.write("\n" + "".join(accumulated))
                        accumulated.clear()
                    output.write(
                        f"[dim]{'─' * 48} done · ${cost:.5f}[/]\n"
                    )
                    status.update("")
                    self._refresh_header()
                    break

                elif etype == "error":
                    err = event.get("error") or event.get("content", "unknown error")
                    if accumulated:
                        output.write("".join(accumulated))
                        accumulated.clear()
                    output.write(f"[red]✗ {err}[/]")
                    status.update("[red]error[/]")
                    break

                elif etype == "context":
                    # Context window info — show once if high
                    pct = event.get("context_percent")
                    if pct and float(pct) > 0.8:
                        status.update(f"[yellow]context {pct:.0%} full — consider /new[/]")

        except httpx.ConnectError:
            output.write(f"[red]✗ Cannot connect to {client.BASE_URL}[/]")
            status.update("[red]connection failed[/]")
        except httpx.HTTPStatusError as e:
            output.write(f"[red]✗ HTTP {e.response.status_code}[/]")
            status.update("[red]request failed[/]")
        except asyncio.CancelledError:
            if accumulated:
                output.write("".join(accumulated) + " [dim](interrupted)[/]")
            status.update("[dim]stopped[/]")
        except Exception as e:
            output.write(f"[red]✗ {e}[/]")
            status.update("[red]error[/]")
        finally:
            # Flush any remaining text_delta not yet written
            if accumulated:
                output.write("".join(accumulated))
            self._streaming = False
            self._task_id = None

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.CANCELLED:
            self._streaming = False
            self._task_id = None

    # ── Slash commands ────────────────────────────────────────────────────────

    def _handle_command(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit"):
            self.exit()

        elif cmd == "/new":
            self._conversation_id = None
            self._spent = 0.0
            self._last_model = "auto"
            self._refresh_header()
            self.query_one(RichLog).clear()
            self._print("[dim]New conversation started.[/]")

        elif cmd == "/stop":
            self._stop_current()

        elif cmd == "/retry":
            self.action_retry()

        elif cmd == "/clear":
            self.action_clear_output()

        elif cmd == "/help":
            self._print(HELP_TEXT)

        elif cmd == "/usage":
            self._fetch_usage()

        elif cmd == "/history":
            self._fetch_history()

        elif cmd == "/skills":
            self._fetch_skills()

        elif cmd == "/memory":
            if not arg:
                self._print("[yellow]Usage: /memory <search query>[/]")
            else:
                self._fetch_memory(arg)

        else:
            self._print(f"[yellow]Unknown command: {cmd}[/]  — try [cyan]/help[/]")

    def _print(self, text: str) -> None:
        self.query_one(RichLog).write(text)

    def _stop_current(self) -> None:
        if not self._streaming:
            self._print("[dim]Nothing running.[/]")
            return
        if self._stream_worker:
            self._stream_worker.cancel()
        if self._task_id:
            asyncio.create_task(client.stop_task(self._task_id))
        self._set_status("[dim]stopping…[/]")

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_interrupt(self) -> None:
        if self._streaming:
            self._stop_current()
        else:
            self.exit()

    def action_clear_output(self) -> None:
        self.query_one(RichLog).clear()
        self._set_status("")

    def action_retry(self) -> None:
        if self._last_query:
            self._run_query(self._last_query)
        else:
            self._print("[dim]Nothing to retry.[/]")

    # ── Background data fetches ───────────────────────────────────────────────

    @work(thread=False)
    async def _fetch_usage(self) -> None:
        data = await client.get_cost_status()
        if not data:
            self._print("[dim]Could not fetch usage data.[/]")
            return
        spent = data.get("spent_month", data.get("total_cost", 0))
        budget = data.get("budget_month", data.get("monthly_budget", 30))
        remaining = float(budget) - float(spent)
        pct = (float(spent) / float(budget) * 100) if budget else 0
        self._print(
            f"\n[bold]Budget usage[/]\n"
            f"  Spent:     [cyan]${float(spent):.4f}[/]\n"
            f"  Remaining: [{'green' if remaining > 5 else 'yellow' if remaining > 1 else 'red'}]${remaining:.4f}[/]\n"
            f"  Monthly:   ${float(budget):.2f}  ({pct:.1f}% used)\n"
        )

    @work(thread=False)
    async def _fetch_history(self) -> None:
        entries = await client.get_history(12)
        if not entries:
            self._print("[dim]No history found (or backend unavailable).[/]")
            return
        lines = ["\n[bold]Recent history[/]"]
        for e in entries[:12]:
            query = str(e.get("query", "")).replace("\n", " ")[:72]
            status = e.get("status", "?")
            cost = e.get("total_cost") or e.get("cost") or 0
            ts = e.get("created_at", "")[:16].replace("T", " ")
            status_color = "green" if status == "completed" else "red" if status == "failed" else "yellow"
            lines.append(
                f"  [{status_color}]●[/] [dim]{ts}[/]  {query}  [dim]${float(cost):.4f}[/]"
            )
        self._print("\n".join(lines) + "\n")

    @work(thread=False)
    async def _fetch_skills(self) -> None:
        skills, growth_areas = await client.get_skills()
        if not skills:
            self._print("[dim]No skills tracked yet.[/]")
            return
        lines = ["\n[bold]Learned skills[/]"]
        for s in skills[:15]:
            name = str(s.get("skill_name") or s.get("skill") or s.get("name") or "?")
            task_type = str(s.get("task_type") or "")
            success = s.get("success_rate") or s.get("success")
            uses = s.get("total_uses") or s.get("count") or s.get("uses") or "?"
            level = str(s.get("proficiency_level") or "")
            success_str = f"{float(success)*100:.0f}%" if success is not None else "—"
            level_color = "green" if level == "expert" else "cyan" if level == "competent" else "dim"
            lines.append(
                f"  [bold]{name}[/] [dim]{task_type}[/]"
                f"  success:{success_str}  uses:{uses}"
                + (f"  [{level_color}]{level}[/]" if level else "")
            )
        if growth_areas:
            lines.append(f"\n  [dim]Growth areas: {', '.join(growth_areas[:6])}[/]")
        self._print("\n".join(lines) + "\n")

    @work(thread=False)
    async def _fetch_memory(self, query: str) -> None:
        results = await client.search_memories(query)
        if not results:
            self._print(f"[dim]No memories matching '{query}'.[/]")
            return
        lines = [f"\n[bold]Memory search:[/] {query}"]
        for m in results:
            content = str(m.get("content", ""))
            cat = str(m.get("category", ""))
            ts = str(m.get("created_at", ""))[:10]
            cat_color = {
                "preference": "magenta", "insight": "green",
                "fact": "blue", "pattern": "yellow",
            }.get(cat, "dim")
            lines.append(f"  [{cat_color}]{cat}[/] [dim]{ts}[/]  {content}")
        self._print("\n".join(lines) + "\n")
