# Remaining work (reconciled checklist)

**Generated:** 2026-05-07  
**Purpose:** Map “what’s left” to concrete files and API routes. Cross-check with `agent_pillars.yaml` and the validator.

## How to run compliance reporting

Config-only scans **under-report** implemented features. Always include a code scan:

```bash
python3 agent_pillar_validator.py --check-code
```

Without `--check-code`, pillar 8 and several orchestration/tool checks only read YAML flags.

| Validator mode | Typical overall score (this repo) |
|----------------|-----------------------------------|
| YAML only | ~75% (misleading) |
| `--check-code` | ~100% on checklist items (still not product “done”) |

The checklist below is **stricter than the validator**: it lists gaps the automated checks do not capture.

---

## Reconciled: validator vs reality

| Item | YAML / config | Code / behavior | Verdict |
|------|-----------------|-----------------|---------|
| Unit tests | Was `enabled: false` | `backend/tests/` (~20 files), `pytest.ini` | Implemented; sync YAML |
| CI | Was `enabled: false` | `.github/workflows/ci.yml` + pytest | Implemented; sync YAML |
| Latency | Was `enabled: false` | `latency_metrics` + `_record_latency_metric` in `agent.py` | Partial — persist works; dashboards/alerts optional |
| Quality / judge | Was `enabled: false` | `quality.score_response_quality`, `_schedule_quality_scoring` | Partial — sampling/ops tuning optional |
| Eval harness | Was `enabled: false` | `backend/evals/run_eval_harness.py`, `test_cases.json` | Starter harness exists; expand cases + CI gate optional |
| Task feedback | Was `enabled: false` | `POST /history/{task_id}/feedback`, `task_feedback`, `save_feedback_learning` | API exists; chat UI thumbs optional |
| Temporal memory | `searchable_by_time_range: true` | `GET /memory/range` + `search_by_time_range` | Implemented |
| MCP | `mcp.enabled: true` | `load_mcp_tools()` + HTTP `MCPClient` | HTTP `/rpc` bridge; stdio/SSE MCP TBD |
| Agent-as-tool | `delegate_sub_agent` | `register_sub_agent_tool` on startup | Exposed as LLM tool |

---

## Recently implemented (2026-05 update)

- **Router sampling** — `ModelRouter.sampling_params_for_model` + orchestrator injects `temperature` / `top_p` on streaming ReAct calls (plan/summary stay at `temperature=0`).
- **MCP (HTTP)** — `ToolRegistry.load_mcp_tools()` at startup; configure `tools.mcp.servers` with `{name, url}` (JSON-RPC at `{url}/rpc`). Stdio/SSE-native MCP still a follow-up.
- **Sub-agent tool** — `delegate_sub_agent` on the main tool registry.
- **`GET /agent/tools/health`** — builtin + MCP readiness snapshot.
- **`GET /memory/range`** — episodic time window (`start` / `end` ISO8601, optional `q`).
- **Memory consolidation** — weekly dedupe job when `memory.lifecycle.consolidation_enabled` is true.
- **CI** — `pytest-cov` + `pytest --cov=app` in GitHub Actions.

## Work still worth doing (by theme)

### Pillar 4 — Tools

| Priority | Task | Where |
|----------|------|--------|
| Medium | Full MCP transports (stdio/SSE) + session management | `mcp_client.py`, `tool_registry.py` |
| Medium | Enable `browser_automation` / `code_execution` in prod (keys + Playwright/E2B) | `tool_registry.py`, env |

### Pillar 5 — Memory

| Priority | Task | Where |
|----------|------|--------|
| Low | Richer consolidation (semantic merge, not just exact duplicates) | `memory.py`, jobs |

### Pillar 3 — LLM router

| Priority | Task | Where |
|----------|------|--------|
| Low | Optional LLM-based routing classifier | `router.py` |

### Pillar 6 — Orchestration

| Priority | Task | Where |
|----------|------|--------|
| Medium | User-defined scheduled tasks (cron), not only internal decay job | `orchestration_runtime.py` or APScheduler/Celery, `schemas/migrations` |
| Medium | Redis-backed queue if you need cross-process durability | New infra; `message_queue` in YAML |
| Low | Dead-letter / `failed_tasks` persistence | `agent_pillars.yaml` `dead_letter`, DB migration |
| Low | Declarative workflows (YAML pipelines) | New module (e.g. `workflows.py`) |

### Pillar 7 — UI

| Priority | Task | Where |
|----------|------|--------|
| Medium | In-chat feedback (thumbs) calling `POST /history/.../feedback` | `frontend/` |
| Low | Slack/Discord parity with Telegram | `integrations/slack_discord_bot.py` |

### Pillar 8 — Testing & evals

| Priority | Task | Where |
|----------|------|--------|
| Medium | Coverage target enforcement in CI (`pytest-cov`) | `.github/workflows/ci.yml`, `pytest.ini` |
| Medium | Expand eval cases + optional merge gate | `backend/evals/test_cases.json`, CI job |
| Low | Latency SLO dashboards / alerts | `latency_metrics` + Grafana or analytics UI |

### Hygiene

| Task | Where |
|------|--------|
| `database.py` migrations placeholder vs real migration story | `backend/app/database.py`, `supabase/` |

---

## API quick reference (feedback, queue, agent)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/agent/run` | Sync run |
| POST | `/agent/stream` | SSE |
| POST | `/agent/enqueue` | Deferred (in-process worker) |
| POST | `/agent/stop` | Cancel |
| GET | `/agent/tools` | Tool list |
| GET | `/agent/tools/health` | Tool / MCP readiness |
| POST | `/history/{task_id}/feedback` | Task feedback + learning hook |
| GET | `/memory/search` | Semantic/FTS |
| GET | `/memory/range` | Memories in `[start, end]` (ISO8601) |

---

## Suggested next steps

1. Add real **MCP server URLs** (or bridge) under `tools.mcp.servers` when you have HTTP JSON-RPC endpoints.  
2. Tune **CI coverage** (`--cov-fail-under=N` in `pytest.ini` or workflow) once baseline is stable.  
3. **User cron / Redis queue** when you outgrow the in-process worker.  
4. **Frontend feedback** wired to `POST /history/.../feedback`.
