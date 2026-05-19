# Implementation Plan

**Created:** 2026-05-19
**Status:** In progress

---

## Priority Order

| # | Item | Effort | Status |
| --- | --- | --- | --- |
| P1 | Scheduling UI | ~1 day | done |
| P2 | Memory & Skills Dashboard | ~2 days | done |
| P3 | Discord Bot | ~2 days | todo |
| P4 | Slack Bot | ~1 day | todo |
| P5 | CLI / TUI | ~3 days | todo |
| P6 | WhatsApp via Meta Cloud API | ~2 days | todo |
| P7 | Modal + SSH terminal backends | ~3 days | todo |
| P8 | DIY Dialectic User Model | ~1 day | done |

---

## P1 — Scheduling UI

**Why first:** Backend is 100% complete (`POST/GET/DELETE /schedules`). Pure frontend gap.

**Implementation:**

- New page: `/app/schedules` in the Next.js frontend
- Cron preset pills + manual expression input
- List view: prompt, cron description, next run, last run, enabled badge, delete button
- Wired to `POST/GET/DELETE /schedules` backend routes

---

## P2 — Memory & Skills Dashboard

**Why second:** Backend fully supports it (`GET /memory/search`, `GET /memory/range`, skill registry). Makes the learning loop visible.

**Implementation:**

- New page: `/app/memory` with two tabs — Memories and Skills
- Memories tab: full-text search input, category filter, timeline view (date + content + relevance score), delete individual memories, add memory manually
- Skills tab: table of learned skill patterns, success rate bar, usage count, growth areas chips

---

## P3 — Discord Bot

**Why third:** The scaffold exists, Telegram is proven, Discord is highest-traffic for developers.

**Implementation:**

- Use `discord.py` (or `py-cord`) — same pattern as `telegram-bot/bot.py`
- New directory: `discord-bot/bot.py`
- Commands: `/ask`, `/task`, `/status` mapped to backend streaming endpoint
- Add `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` env vars to `docker-compose.prod.yml`
- Remove the empty scaffold in `backend/app/integrations/slack_discord_bot.py`

---

## P4 — Slack Bot

**After P3 since patterns are shared.**

**Implementation:**

- `slack-bot/bot.py` using `slack-bolt` with Socket Mode (no public webhook needed)
- Message events routed to backend SSE stream, chunked replies
- `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` env vars
- Socket Mode runs behind NAT/VPS without port exposure

---

## P5 — CLI / TUI

**Implementation:**

- New directory: `cli/` — Python package, entry point `agent` command via `pyproject.toml`
- Use `textual` for full TUI:
  - Multiline input widget (shift+enter = newline, enter = submit)
  - Streaming output panel (tokens arrive via SSE, printed live)
  - Slash-command autocomplete (`/new`, `/retry`, `/undo`, `/model`, `/skills`, `/memory`, `/compress`)
  - Session history sidebar (browse past conversations)
  - Ctrl+C sends `POST /agent/stop` then returns to input
- Reads `BACKEND_API_URL` and `BACKEND_API_KEY` from env

---

## P6 — WhatsApp via Meta Cloud API

**Requires Meta developer app approval and phone number verification.**

**Implementation:**

- `whatsapp-bot/bot.py` using `pywa` or direct Meta Cloud API webhook
- Webhook verification (`GET`) + message handler (`POST`) mounted at `/integrations/whatsapp`
- Voice note handling: audio → Whisper transcription → text query

---

## P7 — Modal + SSH Terminal Backends

**Unblocks "costs nearly nothing when idle" promise.**

**Implementation:**

- New module: `backend/app/tools/backends/`
- `TerminalBackend` abstract class with `LocalBackend`, `E2BBackend`, `ModalBackend`, `SSHBackend`
- Modal: `@modal.function` with persistent volume for workspace, hibernates when idle
- SSH: `paramiko`-based backend for VPS or remote machines
- Config: `AGENT_TERMINAL_BACKEND=modal|e2b|local|ssh` env var

---

## P8 — DIY Dialectic User Model

**Adds a post-session reflection loop that synthesizes memories into a coherent, evolving model of who the user is — no third-party dependency, built on the existing pgvector + memory stack.**

**Why not Honcho/Mem0:** Honcho is purpose-built for this but adds a service dependency. Mem0 is redundant — the project already has semantic memory. The dialectic pattern itself is ~50 lines on top of what already exists.

**Implementation:**

- New `user_model` table: stores a single evolving text document per user (the synthesized persona)
- `run_dialectic_reflection(user_id)`: called after each task completes — fetches recent memories, runs one LLM call to update the user model document
- Reflection prompt: "Based on these memories, update your model of who this user is — goals, preferences, communication style, knowledge level, recurring patterns"
- `get_user_model(user_id)`: retrieves the current model document
- Inject user model into system prompt as a `<user_model>` block (after existing `<retrieved_context>`)
- Config flag `AGENT_DIALECTIC_REFLECTION=true` to enable/disable

---

## Not implementing (for now)

- **Signal** — requires Signal bridge server (`signal-cli` or Matrix); high infra overhead
- **Batch trajectory generation** — research tooling, zero daily-use impact
