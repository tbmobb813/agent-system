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
| ------ | ---------------- | ----------------- | --------- |
| Unit tests | Was `enabled: false` | `backend/tests/` (~20 files), `pytest.ini` | Implemented; sync YAML |
| CI | Was `enabled: false` | `.github/workflows/ci.yml` + pytest | Implemented; sync YAML |
| Latency | Was `enabled: false` | `latency_metrics` + `_record_latency_metric` in `agent.py` | Partial — persist works; dashboards/alerts optional |
| Quality / judge | Was `enabled: false` | `quality.score_response_quality`, `_schedule_quality_scoring` | Partial — sampling/ops tuning optional |
| Eval harness | Was `enabled: false` | `backend/evals/run_eval_harness.py`, `test_cases.json` | Starter harness exists; expand cases + CI gate optional |
| Task feedback | Was `enabled: false` | `POST /history/{task_id}/feedback`, `task_feedback`, `save_feedback_learning`, in-chat thumbs | Implemented; tune UX copy if needed |
| Temporal memory | `searchable_by_time_range: true` | `GET /memory/range` + `search_by_time_range` | Implemented |
| MCP | `mcp.enabled: true` | `load_mcp_tools()` + HTTP `MCPClient` + `McpConnectionHub` (stdio/SSE) | Implemented transports; add real server configs when ready |
| Agent-as-tool | `delegate_sub_agent` | `register_sub_agent_tool` on startup | Exposed as LLM tool |

---

## Recently implemented (2026-05 update)

- **Router sampling** — `ModelRouter.sampling_params_for_model` + orchestrator injects `temperature` / `top_p` on streaming ReAct calls (plan/summary stay at `temperature=0`).
- **MCP (HTTP + stdio/SSE)** — `ToolRegistry.load_mcp_tools()` + `McpConnectionHub`; supports HTTP JSON-RPC bridges and long-lived stdio/SSE sessions from `tools.mcp.servers`.
- **Sub-agent tool** — `delegate_sub_agent` on the main tool registry.
- **`GET /agent/tools/health`** — builtin + MCP readiness snapshot.
- **`GET /memory/range`** — episodic time window (`start` / `end` ISO8601, optional `q`).
- **Memory consolidation** — weekly dedupe job when `memory.lifecycle.consolidation_enabled` is true.
- **Memory consolidation (richer)** — normalization-based dedupe (trim/lower/collapsed whitespace) + optional semantic near-duplicate pass.
- **CI** — `pytest-cov` + `pytest --cov=app --cov-fail-under=55` in GitHub Actions.
- **Queue/runtime** — optional Redis-backed deferred queue, dead-letter persistence (`failed_tasks`), and schedule-dispatch runtime coverage tests.
- **Planner gate** — optional `llm_classifier` planning decision path (with fallback to keyword mode).

## Work still worth doing (by theme)

### Pillar 4 — Tools

| Priority | Task | Where |
|----------|------|--------|
| Done | Reconnect/backoff policy for long-lived stdio/SSE MCP sessions | `mcp_hub.py` |
| Medium | Enable `browser_automation` / `code_execution` in prod (keys + Playwright/E2B) | `tool_registry.py`, env |

### Pillar 5 — Memory

| Priority | Task | Where |
|----------|------|--------|
| Low | Tune semantic consolidation thresholds and sampling cadence | `memory.py`, jobs |

### Pillar 3 — LLM router

| Priority | Task | Where |
|----------|------|--------|
| Low | Tune / monitor LLM classifier quality-vs-latency tradeoff | `router.py`, analytics |

### Pillar 6 — Orchestration

| Priority | Task | Where |
|----------|------|--------|
| Low | Promote schedule dispatch to dedicated worker if load grows | `orchestration_runtime.py`, infra |
| Done | Retry / replay flow over `failed_tasks` dead-letter rows | `POST /agent/dead-letter/{id}/replay` + runtime helper |
| Low | Declarative workflows (YAML pipelines) | New module (e.g. `workflows.py`) |

### Pillar 7 — UI

| Priority | Task | Where |
| ---------- | ------ | -------- |
| Low | Improve feedback discoverability/copy and analytics instrumentation | `frontend/`, `history` APIs |
| Low | Slack/Discord parity with Telegram | `integrations/slack_discord_bot.py` |

### Pillar 8 — Testing & evals

| Priority | Task | Where |
| ---------- | ------ | -------- |
| Low | Raise coverage gate gradually (e.g. 55 → 60) after baseline stabilizes | `.github/workflows/ci.yml`, `pytest.ini` |
| Medium | Expand eval cases + optional merge gate | `backend/evals/test_cases.json`, CI job |
| Low | Latency SLO dashboards / alerts | `latency_metrics` + Grafana or analytics UI |

### Hygiene

| Task | Where |
|------|-------- |
| `database.py` migrations placeholder vs real migration story | `backend/app/database.py`, `supabase/` |

---

## API quick reference (feedback, queue, agent)

| Method | Path | Notes |
| -------- | ------ | -------- |
| POST | `/agent/run` | Sync run |
| POST | `/agent/stream` | SSE |
| POST | `/agent/enqueue` | Deferred (in-process worker) |
| POST | `/agent/stop` | Cancel |
| GET | `/agent/tools` | Tool list |
| GET | `/agent/tools/health` | Tool / MCP readiness |
| POST | `/history/{task_id}/feedback` | Task feedback + learning hook |
| GET | `/memory/search` | Semantic/FTS |
| GET | `/memory/range` | Memories in `[start, end]` (ISO8601) |
| POST | `/agent/schedules` | Create cron schedule (`ScheduledTaskCreate` body) |
| GET | `/agent/schedules` | List schedules (optional `user_id` query) |
| DELETE | `/agent/schedules/{id}` | Delete schedule (optional `user_id` filter) |
| GET | `/agent/stats` | p50/p95/p99 latency by endpoint (`latency_metrics`) |
| POST | `/agent/workflows/{name}/run` | Run YAML workflow from `backend/data/workflows/` |

---

## Suggested next steps

1. Add real **MCP server URLs/commands** under `tools.mcp.servers` (HTTP bridge, SSE, and/or stdio).  
2. Expand **eval harness** cases and add an optional CI merge gate for regressions.  
3. Add **dead-letter replay tooling** (admin endpoint + safe retry semantics).  
4. Raise **coverage gate** incrementally once flaky areas are stabilized.
