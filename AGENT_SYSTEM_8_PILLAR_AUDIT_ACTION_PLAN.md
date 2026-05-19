# Agent System - 8-Pillar Audit & Action Plan

**Date:** May 5, 2026  
**Repo:** <https://github.com/tbmobb813/agent-system>  
**Framework:** AI Agent Development Lifecycle (8 Pillars)

---

## As of 2026-05-07 reconciliation

**Live source of truth for “what’s implemented vs planned”:** [REMAINING_WORK_CHECKLIST.md](REMAINING_WORK_CHECKLIST.md) (run `python3 agent_pillar_validator.py --check-code` for automated cross-check).

The May 5 audit below is **preserved for history**. Items struck through in each pillar’s **Now implemented** subsection were completed after the original audit. Remaining work follows the phased roadmap in this repo’s implementation plan (prompt modularization, eval CI gate, user cron schedules, stdio MCP, PWA, optional advanced items).

---

## Scoring Summary (reconciled 2026-05-07)

| # | Pillar | Original (May 5) | Reconciled | Status |
| --- | -------- | ------------------ | ------------ | -------- |
| 1 | Define Purpose & Scope | 9/10 | 9/10 | Strong; formal `SCOPE.md` added in follow-up work |
| 2 | System Prompt Design | 5/10 | 7/10 | Persona + fiscal injection live; modular `prompts/` package in follow-up |
| 3 | Choose LLM | 8/10 | 8/10 | Solid |
| 4 | Tools & Integrations | 5/10 | 7/10 | Tavily, sub-agent tool, MCP HTTP/SSE, `/agent/tools/health` |
| 5 | Memory Systems | 6/10 | 8/10 | Temporal `GET /memory/range`, `ExecutionState.working_memory`, consolidation job |
| 6 | Orchestration | 6/10 | 7/10 | `POST /agent/enqueue`, optional Redis queue, DLQ `failed_tasks`, scheduler loop |
| 7 | User Interface | 8/10 | 8/10 | Thumbs + `POST /history/.../feedback`; PWA manifest in follow-up |
| 8 | Testing & Evals | 2/10 | 6/10 | pytest suite, CI + coverage floor, latency + quality hooks, eval harness |

**Original overall: 49/80 (61%)**  
**Reconciled overall: 60/80 (75%)**

---

## Pillar 1: Define Purpose & Scope

### What the framework asks for

- Use case definition
- User needs analysis
- Success criteria
- Constraints

### What you have

- **Use case:** Personal AI co-worker for research, coding, analysis, automation
- **User needs:** Single user (you), multi-access (web/Telegram/API), cost-conscious
- **Success criteria:** $30/month budget cap enforced at runtime, accessible everywhere, persistent memory across sessions
- **Constraints:** 2 CPU / 8GB RAM VPS, single-user, open-source stack

### Gaps

- No formal SLA targets (response time, uptime, accuracy)
- No defined "out of scope" boundary - what should the agent refuse?

### Now implemented (2026-05-07)

- ~~Formal scope/SLA doc~~ → **`backend/SCOPE.md`** added in follow-up work (targets + in/out of scope).

### Actions

1. Add `SCOPE.md` defining what the agent does and explicitly does NOT do
2. Define measurable success criteria: p95 response latency < 5s, uptime > 99%, task completion rate tracked

---

## Pillar 2: System Prompt Design

### What the framework asks for

- Goals
- Role/Persona
- Instructions
- Guardrails

### What you have

```python
# orchestrator.py - current system prompt
SYSTEM_PROMPT = """You are a capable personal AI assistant with access to tools.
Guidelines:
- Use tools when you need current information...
- Be concise and direct. Don't explain what you're about to do...
- If a tool fails, try a different approach..."""
```

### Gaps

- **No persona definition** - no name, personality, or communication style
- **No guardrails** - nothing about what the agent should refuse, cost-awareness in responses, or safety boundaries
- **No goal framing** - the prompt doesn't tell the model WHY it exists or what success looks like
- **No output formatting rules** - no structure for how responses should be organized
- **Static prompt** - no dynamic injection of user preferences from memory

### Now implemented (2026-05-07)

- ~~No persona~~ → `build_persona_prompt` + `<assistant_profile>` in [`backend/app/agent/orchestrator.py`](backend/app/agent/orchestrator.py) (see `build_persona_prompt` import; fiscal block ~248–255).
- ~~No guardrails in prompt~~ → Data-only `<retrieved_context>`, profile safety line, `<fiscal_context>` when budget known (same file; modularized to `backend/app/agent/prompts/` in follow-up).
- ~~No goal framing~~ → Plan step + `ExecutionState.goal` / `done_when` + `<progress_checkpoint>` (`_format_progress_checkpoint`, `_compose_system_with_progress`).

### Actions (Priority: HIGH)

1. Create `backend/app/agent/prompts/system_prompt.py` with a structured prompt builder:
   - Base persona + role definition
   - Dynamic context injection (user preferences, memory)
   - Explicit guardrails (cost boundaries, refusal criteria, scope limits)
   - Output formatting instructions
   - Tool usage philosophy (when to use tools vs. answer from knowledge)
2. Add prompt versioning - track which prompt version produced which results
3. Create a `prompts/guardrails.py` module with safety and scope rules

---

## Pillar 3: Choose LLM

### What the framework asks for

- Base model selection
- Parameters (temp, top-p)
- Context window management
- Cost/latency optimization

### What you have

- **ModelRouter** with 8 tiers: free -> simple -> balanced -> coding -> research -> advanced -> premium -> agent
- **Complexity-based classification** using keyword matching
- **Fallback chains** for model failures
- **Budget-aware routing** - forces cheaper models when budget is low
- **Context window management** - auto-compaction at 75%, sliding summarization

### Gaps

- **No parameter tuning** - temperature and top-p aren't configurable per tier or task type
- **Keyword-based classification is brittle** - "write a function" routes to coding, but "help me think through this architecture" might miss "complex"
- **No A/B testing** - can't compare model quality across routing decisions
- **No latency tracking per model** - you track cost but not speed

### Now implemented (2026-05-07)

- ~~No per-tier sampling~~ → `ModelRouter.sampling_params_for_model` + orchestrator injection for ReAct calls ([`backend/app/agent/router.py`](backend/app/agent/router.py), orchestrator).
- ~~No latency tracking~~ → `_record_latency_metric` in [`backend/app/routes/agent.py`](backend/app/routes/agent.py); persisted for analysis.
- **A/B testing** → [`backend/app/agent/ab_testing.py`](backend/app/agent/ab_testing.py) exists (wiring optional).
- **Optional** → LLM classifier + `/agent/model-stats` remain nice-to-haves.

### Actions

1. Add `temperature` and `top_p` to each model tier config in `router.py`
2. Consider an LLM-based classifier as a lightweight pre-pass (use free model to classify, then route)
3. Log latency per model per request in the cost_tracking table
4. Add model performance comparison endpoint: `/agent/model-stats`

---

## Pillar 4: Tools & Integrations

### What the framework asks for

- Simple (local) tools
- API integrations (web, apps, data)
- MCP server support
- AI agent as a tool
- Custom functions

### What you have

- **ToolRegistry** with 6 built-in tools: web_search, browser_automation, file_operations, code_execution, api_call, search_documents
- **Parallel tool execution** in the ReAct loop
- **Tool schema generation** for LLM function calling
- Placeholder implementations (several tools log "not yet implemented")

### Gaps

- **MCP server integration** - mentioned in docs ("Extensible via MCP") but no actual implementation
- **Agent-as-a-tool** - no sub-agent invocation pattern
- **Several tools are stubs** - browser_automation returns placeholder, code_execution needs E2B key
- **No tool health checks** - if Tavily is down, you find out at runtime
- **No tool versioning or capability registry**

### Now implemented (2026-05-07)

- ~~No MCP~~ → HTTP JSON-RPC [`backend/app/tools/mcp_client.py`](backend/app/tools/mcp_client.py); SSE hub [`backend/app/tools/mcp_hub.py`](backend/app/tools/mcp_hub.py); `load_mcp_tools()` at startup ([`backend/app/main.py`](backend/app/main.py)).
- ~~No sub-agent~~ → `delegate_sub_agent` on tool registry + [`backend/app/agent/sub_agent.py`](backend/app/agent/sub_agent.py).
- ~~No health endpoint~~ → `GET /agent/tools/health`.
- **Still partial** → browser/E2B in prod, stdio MCP (follow-up), tool versioning registry.

### Actions (Priority: HIGH)

1. Implement real tool functions - at minimum: web_search (Tavily), code_execution (E2B or local sandbox)
2. Add MCP client in `backend/app/tools/mcp_client.py` - connect to external MCP servers
3. Create `backend/app/agent/sub_agent.py` - allow orchestrator to spawn sub-agents as tools
4. Add tool health check endpoint: `/agent/tools/health`
5. Create `backend/app/tools/custom/` directory with a template for user-defined tools

---

## Pillar 5: Memory Systems

### What the framework asks for

- Episodic memory (conversation-level)
- Working memory (within-session)
- Vector database
- SQL/structured DB
- File storage

### What you have

- **pgvector semantic search** with 1536-dim embeddings (text-embedding-3-small)
- **Full-text search fallback** when no OpenAI key
- **Memory categories:** context, preference, fact, pattern
- **Auto-save insights** after each conversation (extract_insight via LLM)
- **Conversation history** with context compaction
- **Document storage** with semantic search (doc_context_for_query)

### Gaps

- **No true episodic memory** - conversations are stored but not indexed by session/episode with temporal context (when did this happen, what was the broader context)
- **No working memory** - within a single session, there's no scratchpad for intermediate reasoning state that persists across tool calls
- **No memory decay/pruning** - memories accumulate forever; no relevance decay over time
- **No memory consolidation** - short-term facts aren't promoted to long-term patterns automatically
- **File storage** - documents can be uploaded but there's no structured file management

### Now implemented (2026-05-07)

- ~~No temporal queries~~ → `GET /memory/range` + `search_by_time_range` ([`backend/app/agent/memory.py`](backend/app/agent/memory.py), routes).
- ~~No working memory~~ → `ExecutionState.working_memory` in orchestrator (ReAct trace across iterations).
- ~~No consolidation~~ → Weekly dedupe/consolidation when enabled in pillar config ([`REMAINING_WORK_CHECKLIST.md`](REMAINING_WORK_CHECKLIST.md)).
- **Still partial** → semantic-merge consolidation, richer file management.

### Actions

1. Add `session_id` and `timestamp_range` to memory table - enable temporal queries ("what did we discuss last week")
2. Create a working memory scratchpad in `ExecutionState` that persists across iterations within a single run
3. Implement memory decay: reduce `relevance_score` over time, prune low-relevance memories monthly
4. Add memory consolidation job - periodically analyze memories to extract patterns from facts
5. Integrate file storage paths into the memory system so document references are queryable

---

## Pillar 6: Orchestration

### What the framework asks for

- Routes/workflows
- Triggers (scheduled, event-driven)
- Parameters
- Message queues
- Agent2Agent communication
- Error handling

### What you have

- **ReAct loop** with plan-then-execute for complex queries
- **Parallel tool execution** with asyncio.gather
- **Fallback chains** - model failures cascade through alternatives
- **Max iteration safety** - prevents infinite loops
- **Task state tracking** - ExecutionState with step counts and error lists
- **Conversation compaction** - auto-summarize when context window fills

### Gaps

- **No triggers** - everything is user-initiated; no scheduled tasks, no cron-like runs
- **No message queues** - tasks execute synchronously or stream; no deferred execution
- **No Agent2Agent** - can't delegate sub-tasks to specialized agents
- **No workflow definitions** - no way to define multi-step workflows declaratively
- **Error handling is basic** - fallback chain for model errors, but no retry with exponential backoff, no dead-letter queue

### Now implemented - Orchestration (2026-05-07)

- ~~No deferred execution~~ → `POST /agent/enqueue` + in-process worker ([`backend/app/agent/orchestration_runtime.py`](backend/app/agent/orchestration_runtime.py)).
- ~~No queue~~ → Optional Redis-backed queue when configured + `REDIS_URL`.
- ~~No Agent2Agent~~ → Sub-agent / `delegate_sub_agent`.
- ~~No DLQ~~ → `failed_tasks` migration + `_persist_failed_task` when pillar `dead_letter` enabled.
- **Still partial** → User-defined cron API (follow-up), workflow YAML DSL, Celery/RQ for multi-process.

### Actions

1. Add `backend/app/scheduler/` with APScheduler or Celery Beat for scheduled tasks
2. Create workflow DSL in `backend/app/agent/workflows.py` - define multi-step pipelines as YAML/JSON
3. Implement Agent2Agent via the sub-agent pattern (Pillar 4 action #3)
4. Add Redis-backed message queue for deferred task execution
5. Implement structured error recovery: retry policies, circuit breakers, dead-letter logging

---

## Pillar 7: User Interface

### What the framework asks for

- Chat interface
- Web app
- API endpoint
- Slack/Discord bot

### What you have

- **Web dashboard** - Next.js 15 with dark/light mode, real-time streaming, cost tracking, history, settings, documents, commands pages
- **API endpoints** - FastAPI with /agent/run, /agent/stream, /agent/tools, /agent/models, full Swagger docs
- **Telegram bot** - /ask, /code, /analyze, /history, /status, /help commands with real-time processing
- **SSE streaming** - token-by-token response display

### Gaps

- **No Slack/Discord bot** - slot is identified but not built
- **Frontend is partially skeleton** - some components need implementation (AgentExecutor, CostTracker detail views)
- **No mobile-native app** - web is responsive but no PWA or native app
- **No feedback mechanism** - no thumbs up/down or rating on responses

### Now implemented (2026-05-07)

- ~~No feedback~~ → `submitTaskFeedback` + thumbs in [`frontend/components/AgentExecutor.tsx`](frontend/components/AgentExecutor.tsx) and [`frontend/components/TaskHistory.tsx`](frontend/components/TaskHistory.tsx); API `POST /history/{task_id}/feedback`.
- **Still partial** → Slack/Discord, PWA manifest (follow-up).

### Actions

1. Add user feedback collection: thumbs up/down + optional text on each response
2. Store feedback in a `response_feedback` table for quality tracking (feeds Pillar 8)
3. Consider PWA manifest for mobile - low effort, high value
4. Slack/Discord bot is lower priority but template exists in telegram-bot pattern

---

## Pillar 8: Testing & Evals

### What the framework asks for

- Unit tests
- Latency testing
- Quality metrics
- Iterate & improve loop

### What you have

- **Deployment checklist** - manual verification steps
- **Health check endpoint** - `/health`
- **Basic logging** - structured Python logging
- Screenshot shows "Running 5 tests using 2 workers - 5 passed (16.3s)"

### Gaps (CRITICAL - weakest pillar)

- **No test suite** - no pytest tests for orchestrator, router, memory, tools
- **No latency benchmarks** - no p50/p95/p99 response time tracking
- **No quality metrics** - no way to measure if responses are good
- **No eval framework** - no automated evaluation of agent outputs against expected results
- **No regression testing** - prompt changes could degrade quality silently
- **No CI/CD integration** - no GitHub Actions running tests on push

### Now implemented (2026-05-07)

- ~~No test suite~~ → [`backend/tests/`](backend/tests/) (router, memory, tools, orchestrator, etc.).
- ~~No CI~~ → [`.github/workflows/ci.yml`](.github/workflows/ci.yml) with pytest + `--cov-fail-under`.
- ~~No latency~~ → `_record_latency_metric` in [`backend/app/routes/agent.py`](backend/app/routes/agent.py).
- ~~No quality~~ → [`backend/app/agent/quality.py`](backend/app/agent/quality.py) + `_schedule_quality_scoring`.
- ~~No eval harness~~ → [`backend/evals/run_eval_harness.py`](backend/evals/run_eval_harness.py) + `test_cases.json` (CI eval job in follow-up).
- **Still partial** → Grafana-style SLO dashboards, eval merge gate strictness, expanded case library.

### Actions (Priority: CRITICAL)

1. Create `backend/tests/` with pytest:
   - `test_router.py` - verify query classification maps to correct model tiers
   - `test_memory.py` - verify save/search/context_for_query
   - `test_tools.py` - verify tool registry, schema generation, error handling
   - `test_orchestrator.py` - verify ReAct loop terminates, handles failures
2. Add latency instrumentation: track and store p50/p95/p99 per endpoint
3. Create `backend/evals/` with an evaluation harness:
   - Define test cases as JSON: input query -> expected behavior (tool calls, output patterns)
   - Run against live agent, score outputs
   - Track scores over time
4. Add response quality scoring:
   - Use a judge LLM to rate agent responses on helpfulness/accuracy/conciseness
   - Store scores in `response_quality` table
5. Set up GitHub Actions: run tests on push, block merge on failure

---

## Priority Action Roadmap

**Superseded (2026-05-07):** The original week-by-week table below reflected the May 5 snapshot. Most “Phase 1” and parts of “Phase 2/3” are now shipped — see [REMAINING_WORK_CHECKLIST.md](REMAINING_WORK_CHECKLIST.md) and pillar **Now implemented** notes above.

**Current focus:** prompt modularization (`backend/app/agent/prompts/`), eval expansion + CI eval job, `SCOPE.md`, user cron schedules + `scheduled_tasks` table, stdio MCP, PWA manifest, and optional advanced items (workflow DSL, semantic merge, `/agent/stats`, LLM router, Slack/Discord, prod browser/E2B).

<details>
<summary>Original roadmap (historical)</summary>

### Phase 1 - Foundation (Week 1-2)

| Action | Pillar | Effort | Impact |
|--------|--------|--------|--------|
| Create pytest test suite | 8 | 4-6 hrs | Critical |
| Build structured system prompt | 2 | 2-3 hrs | High |
| Implement real tool functions | 4 | 4-6 hrs | High |
| Add latency + quality tracking | 8 | 3-4 hrs | High |

### Phase 2 - Memory & Orchestration (Week 3-4)

| Action | Pillar | Effort | Impact |
|--------|--------|--------|--------|
| Add episodic memory + working memory | 5 | 4-6 hrs | High |
| Create eval harness with test cases | 8 | 4-6 hrs | High |
| Add scheduled tasks (triggers) | 6 | 3-4 hrs | Medium |
| User feedback collection | 7 | 2-3 hrs | Medium |

### Phase 3 - Advanced (Week 5-8)

| Action | Pillar | Effort | Impact |
|--------|--------|--------|--------|
| MCP client integration | 4 | 4-6 hrs | Medium |
| Workflow DSL for multi-step pipelines | 6 | 6-8 hrs | Medium |
| Agent2Agent sub-agent pattern | 4/6 | 4-6 hrs | Medium |
| CI/CD with GitHub Actions | 8 | 2-3 hrs | Medium |
| Memory decay + consolidation | 5 | 3-4 hrs | Low |
| LLM-based query classifier | 3 | 2-3 hrs | Low |

</details>

---

## Cross-Cutting: Universal LLM Guidelines Integration

Your `UNIVERSAL_LLM_GUIDELINES.md` (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) should be enforced across the agent system itself. Specifically:

- **Think Before Coding** -> The plan-then-execute pattern in orchestrator already embodies this. Extend it to all complex tool chains.
- **Simplicity First** -> Router should prefer simpler models first (already does via cost tiers). Prompt design should enforce concise outputs.
- **Surgical Changes** -> Memory updates should be minimal and targeted, not wholesale rewrites.
- **Goal-Driven Execution** -> Every agent run should log its goal, track progress against it, and evaluate success at completion (feeds into evals).
