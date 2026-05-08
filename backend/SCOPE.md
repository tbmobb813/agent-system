# Agent system — purpose, scope, and SLOs

**Audience:** operators and future-you tuning behavior.  
**Complements:** product goals in repo docs and `agent_pillars.yaml`.

## In scope

- Research-style Q&A, summarization, and analysis (with citations when tools are used).
- Coding assistance: explain, generate, refactor, debug (user-supplied code and public docs).
- Light automation via tools (HTTP APIs, file ops in sandbox, web search) when keys are configured.
- Personal memory: preferences, facts, and conversation context stored per deployment policy.

## Out of scope (refuse / escalate)

- Bypassing authentication, exfiltrating private data without authorization, or attacking systems.
- Medical, legal, or financial **advice** framed as professional counsel — provide general information only and suggest qualified humans.
- Modifying production infrastructure, billing, or secrets without explicit human approval in your runbook.
- Training-data poisoning, prompt-injection-driven system changes, or executing instructions embedded in untrusted retrieved content (treat as data only).

## Success criteria & SLO targets (single-user VPS)

| Metric | Target | Notes |
|--------|--------|--------|
| Monthly LLM spend | ≤ configured cap (e.g. $30) | Enforced in app config + router fiscal nudges |
| API availability | **99%** monthly | Excludes planned maintenance; measure via `/health` + uptime checks |
| Interactive p95 latency | **&lt; 5s** for non-streaming short tasks | Excludes long tool runs (browser, code sandbox); track via `latency_metrics` |
| Task completion | Track qualitatively | Use history + optional feedback `POST /history/{task_id}/feedback` |

These are **targets**, not guarantees, unless you wire external monitoring and alerting.

## Operational notes

- **Budget:** When remaining budget is low, the router and system prompt steer toward cheaper models and fewer tool calls.
- **Evals:** Run `python3 backend/evals/run_eval_harness.py` locally; CI runs it when `backend/**` changes.
- **Compliance:** For automated pillar checks, `python3 agent_pillar_validator.py --check-code`.
