#!/usr/bin/env python3
"""
Agent 8-Pillar Validator
========================
Reads agent_pillars.yaml and validates that all 8 pillars are properly
configured. Produces a compliance report with scores, gaps, and next actions.

Usage:
    python agent_pillar_validator.py                    # Check config
    python agent_pillar_validator.py --check-code       # Also scan codebase
    python agent_pillar_validator.py --json              # JSON output
    python agent_pillar_validator.py --ci                # Exit code 1 if score < threshold

Legacy path (kept for compatibility):
    python "python agent_pillar_validator.py"
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "info"  # info | warning | critical
    action: str = ""


@dataclass
class PillarReport:
    number: int
    name: str
    score: int  # 0-10
    max_score: int = 10
    checks: list = field(default_factory=list)
    status: str = ""  # ✅ Strong | ⚠️ Partial | 🔴 Critical

    def compute_status(self):
        if self.score >= 8:
            self.status = "✅ Strong"
        elif self.score >= 5:
            self.status = "⚠️ Partial"
        else:
            self.status = "🔴 Critical"


# ─────────────────────────────────────────────────────────────────────────────
# Pillar validators
# ─────────────────────────────────────────────────────────────────────────────


def validate_pillar_1(cfg: dict) -> PillarReport:
    """Define Purpose & Scope"""
    report = PillarReport(1, "Define Purpose & Scope", 0)
    p = cfg.get("purpose", {})

    checks = [
        Check(
            "Use case defined", bool(p.get("use_case")), p.get("use_case", "MISSING")
        ),
        Check(
            "User type defined",
            p.get("user_type") in ("single_user", "multi_user"),
            f"user_type={p.get('user_type', 'MISSING')}",
        ),
        Check(
            "Success criteria defined",
            bool(p.get("success_criteria")),
            f"{len(p.get('success_criteria', {}))} criteria",
        ),
        Check(
            "Budget limit set",
            p.get("success_criteria", {}).get("max_monthly_budget_usd", 0) > 0,
            f"${p.get('success_criteria', {}).get('max_monthly_budget_usd', 'MISSING')}/month",
        ),
        Check(
            "Latency target set",
            p.get("success_criteria", {}).get("target_p95_latency_ms", 0) > 0,
            f"{p.get('success_criteria', {}).get('target_p95_latency_ms', 'MISSING')}ms",
            severity="warning",
            action="Set target_p95_latency_ms in success_criteria",
        ),
        Check(
            "Constraints defined",
            bool(p.get("constraints")),
            f"{len(p.get('constraints', {}))} constraints",
        ),
        Check(
            "Out of scope defined",
            len(p.get("out_of_scope", [])) > 0,
            f"{len(p.get('out_of_scope', []))} exclusions",
            severity="warning",
            action="Define what the agent should NOT do",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_2(cfg: dict) -> PillarReport:
    """System Prompt Design"""
    report = PillarReport(2, "System Prompt Design", 0)
    sp = cfg.get("system_prompt", {})

    persona = sp.get("persona", {})
    checks = [
        Check(
            "Persona name defined",
            bool(persona.get("name")),
            persona.get("name", "MISSING"),
            severity="warning",
            action="Give the agent a name/identity",
        ),
        Check(
            "Role defined", bool(persona.get("role")), persona.get("role", "MISSING")
        ),
        Check(
            "Personality defined",
            bool(persona.get("personality")),
            persona.get("personality", "MISSING")[:50],
            severity="warning",
        ),
        Check(
            "Goals defined",
            len(sp.get("goals", [])) >= 2,
            f"{len(sp.get('goals', []))} goals",
        ),
        Check(
            "Instructions defined",
            len(sp.get("instructions", [])) >= 2,
            f"{len(sp.get('instructions', []))} instructions",
        ),
        Check(
            "Guardrails defined",
            len(sp.get("guardrails", [])) >= 3,
            f"{len(sp.get('guardrails', []))} guardrails",
            severity="critical",
            action="Add guardrails for safety and scope enforcement",
        ),
        Check(
            "Dynamic context injection",
            sp.get("dynamic_context", {}).get("inject_user_preferences", False),
            (
                "User preferences injected"
                if sp.get("dynamic_context", {}).get("inject_user_preferences")
                else "Static prompt only"
            ),
            severity="warning",
        ),
        Check(
            "Prompt versioning",
            sp.get("versioning", {}).get("track_prompt_versions", False),
            (
                "Versioning enabled"
                if sp.get("versioning", {}).get("track_prompt_versions")
                else "No versioning"
            ),
            severity="warning",
            action="Enable prompt versioning to track quality changes",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_3(cfg: dict) -> PillarReport:
    """Choose LLM"""
    report = PillarReport(3, "Choose LLM", 0)
    llm = cfg.get("llm", {})
    tiers = llm.get("model_tiers", {})

    complexity_mode = (
        (cfg.get("orchestration", {}) or {})
        .get("execution", {})
        .get("complexity_threshold", "keyword")
    )
    checks = [
        Check(
            "Provider configured",
            bool(llm.get("provider")),
            llm.get("provider", "MISSING"),
        ),
        Check("Multiple model tiers", len(tiers) >= 3, f"{len(tiers)} tiers defined"),
        Check(
            "Temperature configured per tier",
            all("temperature" in t for t in tiers.values()),
            (
                "All tiers have temperature"
                if all("temperature" in t for t in tiers.values())
                else "Some tiers missing temperature"
            ),
            severity="warning",
        ),
        Check(
            "Fallback chain defined",
            len(llm.get("fallback_chain", [])) >= 2,
            f"{len(llm.get('fallback_chain', []))} models in chain",
        ),
        Check(
            "Context window configured",
            llm.get("context_window", {}).get("max_tokens", 0) > 0,
            f"{llm.get('context_window', {}).get('max_tokens', 'MISSING')} tokens",
        ),
        Check(
            "Compaction strategy",
            llm.get("context_window", {}).get("compaction_trigger_percent", 0) > 0,
            f"Triggers at {llm.get('context_window', {}).get('compaction_trigger_percent', 'MISSING')}%",
        ),
        Check(
            "Latency tracking enabled",
            llm.get("tracking", {}).get("log_latency_per_model", False),
            (
                "Enabled"
                if llm.get("tracking", {}).get("log_latency_per_model")
                else "Disabled"
            ),
            severity="warning",
            action="Enable latency tracking per model",
        ),
        Check(
            "Tool-capable tiers identified",
            any(t.get("supports_tools") for t in tiers.values()),
            f"{sum(1 for t in tiers.values() if t.get('supports_tools'))} tiers support tools",
        ),
        Check(
            "Routing classifier configured for llm_classifier mode",
            complexity_mode != "llm_classifier"
            or bool(llm.get("routing_classifier", {}).get("model")),
            llm.get("routing_classifier", {}).get(
                "model", "not required (keyword mode)"
            ),
            severity="warning",
            action="Set llm.routing_classifier.model when using complexity_threshold=llm_classifier",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_4(cfg: dict) -> PillarReport:
    """Tools & Integrations"""
    report = PillarReport(4, "Tools & Integrations", 0)
    tools = cfg.get("tools", {})
    builtin = tools.get("builtin", {})
    code = cfg.get("__code_facts__", {})
    discovered_mcp = bool(code.get("mcp_integration_present", False))
    discovered_agent_tool = bool(code.get("agent_as_tool_present", False))

    enabled_tools = [k for k, v in builtin.items() if v.get("enabled")]
    has_health = [k for k, v in builtin.items() if v.get("health_check")]

    checks = [
        Check(
            "Builtin tools defined", len(builtin) >= 3, f"{len(builtin)} tools defined"
        ),
        Check(
            "Tools enabled",
            len(enabled_tools) >= 2,
            f"{len(enabled_tools)} enabled: {', '.join(enabled_tools)}",
            severity="warning",
            action="Enable more tools (browser_automation, code_execution)",
        ),
        Check(
            "Health checks configured",
            len(has_health) >= 1,
            f"{len(has_health)} tools with health checks",
            severity="warning",
        ),
        Check(
            "MCP integration",
            tools.get("mcp", {}).get("enabled", False) or discovered_mcp,
            (
                "Enabled (HTTP and/or stdio/SSE hub)"
                if (tools.get("mcp", {}).get("enabled", False) or discovered_mcp)
                else "Not yet implemented"
            ),
            severity="warning",
            action="Implement MCP tool loading (HTTP bridge and/or persistent stdio/SSE sessions)",
        ),
        Check(
            "Agent-as-tool",
            tools.get("agent_as_tool", {}).get("enabled", False)
            or discovered_agent_tool,
            (
                "Enabled"
                if (
                    tools.get("agent_as_tool", {}).get("enabled", False)
                    or discovered_agent_tool
                )
                else "Not yet implemented"
            ),
            severity="warning",
            action="Implement sub-agent pattern",
        ),
        Check(
            "Custom functions directory",
            bool(tools.get("custom_functions", {}).get("directory")),
            tools.get("custom_functions", {}).get("directory", "MISSING"),
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_5(cfg: dict) -> PillarReport:
    """Memory Systems"""
    report = PillarReport(5, "Memory Systems", 0)
    mem = cfg.get("memory", {})
    code = cfg.get("__code_facts__", {})
    discovered_temporal = bool(code.get("memory_temporal_search_present", False))
    discovered_working_memory = bool(code.get("working_memory_present", False))
    discovered_decay = bool(code.get("memory_decay_present", False))

    checks = [
        Check(
            "Episodic memory",
            mem.get("episodic", {}).get("enabled", False),
            "Enabled" if mem.get("episodic", {}).get("enabled") else "Disabled",
        ),
        Check(
            "Episodic temporal search",
            mem.get("episodic", {}).get("searchable_by_time_range", False)
            or discovered_temporal,
            (
                "Temporal queries supported"
                if (
                    mem.get("episodic", {}).get("searchable_by_time_range", False)
                    or discovered_temporal
                )
                else "No temporal search"
            ),
            severity="warning",
            action="Enable time-range queries on episodic memory",
        ),
        Check(
            "Working memory",
            mem.get("working_memory", {}).get("enabled", False)
            or discovered_working_memory,
            (
                "Enabled"
                if (
                    mem.get("working_memory", {}).get("enabled", False)
                    or discovered_working_memory
                )
                else "Not implemented"
            ),
            severity="warning",
            action="Implement session scratchpad in ExecutionState",
        ),
        Check(
            "Vector database",
            mem.get("vector_database", {}).get("enabled", False),
            f"pgvector {mem.get('vector_database', {}).get('embedding_dimensions', '?')}d",
        ),
        Check(
            "Structured DB",
            mem.get("structured_db", {}).get("enabled", False),
            f"{len(mem.get('structured_db', {}).get('tables', []))} tables",
        ),
        Check(
            "File storage",
            mem.get("file_storage", {}).get("enabled", False),
            f"Max {mem.get('file_storage', {}).get('max_size_mb', '?')}MB",
        ),
        Check(
            "Auto insight extraction",
            mem.get("lifecycle", {}).get("auto_save_insights", False),
            (
                "Enabled"
                if mem.get("lifecycle", {}).get("auto_save_insights")
                else "Disabled"
            ),
        ),
        Check(
            "Memory decay",
            mem.get("lifecycle", {}).get("decay_enabled", False) or discovered_decay,
            (
                f"Half-life {mem.get('lifecycle', {}).get('decay_half_life_days', 'N/A')} days"
                if (
                    mem.get("lifecycle", {}).get("decay_enabled", False)
                    or discovered_decay
                )
                else "No decay — memories grow forever"
            ),
            severity="warning",
            action="Implement relevance decay to prevent memory bloat",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_6(cfg: dict) -> PillarReport:
    """Orchestration"""
    report = PillarReport(6, "Orchestration", 0)
    orch = cfg.get("orchestration", {})
    code = cfg.get("__code_facts__", {})
    discovered_scheduler = bool(code.get("scheduled_triggers_present", False))
    discovered_events = bool(code.get("event_triggers_present", False))
    discovered_queue = bool(code.get("message_queue_present", False))
    discovered_agent2agent = bool(code.get("agent2agent_present", False))
    discovered_circuit_breaker = bool(code.get("circuit_breaker_present", False))
    discovered_dead_letter = bool(code.get("dead_letter_present", False))

    checks = [
        Check(
            "Execution mode defined",
            orch.get("execution", {}).get("mode")
            in ("react", "plan_and_execute", "simple"),
            f"Mode: {orch.get('execution', {}).get('mode', 'MISSING')}",
        ),
        Check(
            "Parallel tool calls",
            orch.get("execution", {}).get("parallel_tool_calls", False),
            (
                "Enabled"
                if orch.get("execution", {}).get("parallel_tool_calls")
                else "Sequential only"
            ),
        ),
        Check(
            "Plan complex queries",
            orch.get("execution", {}).get("plan_complex_queries", False),
            "Enabled",
        ),
        Check(
            "Scheduled triggers",
            orch.get("triggers", {}).get("scheduled_tasks", {}).get("enabled", False)
            or discovered_scheduler,
            (
                "Enabled"
                if (
                    orch.get("triggers", {}).get("scheduled_tasks", {}).get("enabled")
                    or discovered_scheduler
                )
                else "No scheduled tasks"
            ),
            severity="warning",
            action="Implement scheduled task runner (APScheduler/Celery)",
        ),
        Check(
            "Event triggers",
            orch.get("triggers", {}).get("event_driven", {}).get("enabled", False)
            or discovered_events,
            (
                "Enabled"
                if (
                    orch.get("triggers", {}).get("event_driven", {}).get("enabled")
                    or discovered_events
                )
                else "No event triggers"
            ),
            severity="warning",
        ),
        Check(
            "Message queue",
            orch.get("message_queue", {}).get("enabled", False) or discovered_queue,
            (
                "Enabled"
                if (orch.get("message_queue", {}).get("enabled") or discovered_queue)
                else "No queue — all synchronous"
            ),
            severity="warning",
            action="Add Redis queue for deferred execution",
        ),
        Check(
            "Agent2Agent",
            orch.get("agent2agent", {}).get("enabled", False) or discovered_agent2agent,
            (
                "Enabled"
                if (
                    orch.get("agent2agent", {}).get("enabled") or discovered_agent2agent
                )
                else "Single agent only"
            ),
            severity="warning",
        ),
        Check(
            "Model fallback chain",
            orch.get("error_handling", {}).get("model_fallback", False),
            "Enabled",
        ),
        Check(
            "Circuit breaker",
            orch.get("error_handling", {})
            .get("circuit_breaker", {})
            .get("enabled", False)
            or discovered_circuit_breaker,
            (
                "Enabled"
                if (
                    orch.get("error_handling", {})
                    .get("circuit_breaker", {})
                    .get("enabled")
                    or discovered_circuit_breaker
                )
                else "No circuit breaker"
            ),
            severity="warning",
        ),
        Check(
            "Dead-letter persistence",
            orch.get("error_handling", {}).get("dead_letter", {}).get("enabled", False)
            or discovered_dead_letter,
            (
                "Enabled"
                if (
                    orch.get("error_handling", {}).get("dead_letter", {}).get("enabled")
                    or discovered_dead_letter
                )
                else "Disabled"
            ),
            severity="info",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_7(cfg: dict) -> PillarReport:
    """User Interface"""
    report = PillarReport(7, "User Interface", 0)
    ui = cfg.get("user_interface", {})
    code = cfg.get("__code_facts__", {})
    discovered_feedback = bool(code.get("feedback_mechanism_present", False))
    discovered_slack_discord = bool(code.get("slack_discord_bot_present", False))

    checks = [
        Check(
            "Chat interface",
            ui.get("chat_interface", {}).get("enabled", False),
            ui.get("chat_interface", {}).get("provider", "MISSING"),
        ),
        Check(
            "Web app",
            ui.get("web_app", {}).get("enabled", False),
            f"{len(ui.get('web_app', {}).get('pages', []))} pages",
        ),
        Check(
            "API endpoint",
            ui.get("api_endpoint", {}).get("enabled", False),
            f"{len(ui.get('api_endpoint', {}).get('endpoints', []))} endpoints",
        ),
        Check(
            "Telegram bot",
            ui.get("telegram_bot", {}).get("enabled", False),
            f"{len(ui.get('telegram_bot', {}).get('commands', []))} commands",
        ),
        Check(
            "Slack/Discord bot",
            ui.get("slack_discord_bot", {}).get("enabled", False)
            or discovered_slack_discord,
            (
                "Enabled"
                if (
                    ui.get("slack_discord_bot", {}).get("enabled", False)
                    or discovered_slack_discord
                )
                else "Not implemented"
            ),
            severity="info",
        ),
        Check(
            "User feedback collection",
            ui.get("feedback", {}).get("enabled", False) or discovered_feedback,
            (
                "Enabled"
                if (ui.get("feedback", {}).get("enabled") or discovered_feedback)
                else "No feedback mechanism"
            ),
            severity="warning",
            action="Add thumbs up/down + comments on responses",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


def validate_pillar_8(cfg: dict) -> PillarReport:
    """Testing & Evals"""
    report = PillarReport(8, "Testing & Evals", 0)
    test = cfg.get("testing", {})
    code = cfg.get("__code_facts__", {})

    discovered_tests = int(code.get("pytest_test_files", 0) or 0)
    discovered_pytest = bool(code.get("pytest_config_present", False))
    discovered_latency = bool(code.get("latency_instrumentation_present", False))
    discovered_eval_harness = bool(code.get("eval_harness_present", False))
    discovered_quality = bool(code.get("quality_scoring_present", False))
    discovered_ci = bool(code.get("ci_pipeline_present", False))
    discovered_cov_gate = bool(code.get("coverage_gate_present", False))
    discovered_feedback_loop = bool(code.get("feedback_loop_present", False))
    unit_tests_enabled = test.get("unit_tests", {}).get("enabled", False)
    effective_unit_tests_enabled = unit_tests_enabled or (
        discovered_pytest and discovered_tests > 0
    )
    unit_test_detail = (
        f"pytest in {test.get('unit_tests', {}).get('test_directory', 'N/A')}"
        if effective_unit_tests_enabled
        else "NO TEST SUITE"
    )
    if discovered_pytest and discovered_tests > 0:
        unit_test_detail += f" (detected {discovered_tests} test files)"

    checks = [
        Check(
            "Unit tests",
            effective_unit_tests_enabled,
            unit_test_detail,
            severity="critical",
            action="Create backend/tests/ with pytest tests for all core modules",
        ),
        Check(
            "Min coverage target",
            test.get("unit_tests", {}).get("min_coverage_percent", 0) >= 50,
            f"{test.get('unit_tests', {}).get('min_coverage_percent', 0)}% target",
            severity="critical",
        ),
        Check(
            "Latency tracking",
            test.get("latency_testing", {}).get("enabled", False) or discovered_latency,
            (
                "p50/p95/p99 tracked"
                if (
                    test.get("latency_testing", {}).get("enabled", False)
                    or discovered_latency
                )
                else "No latency metrics"
            ),
            severity="critical",
            action="Instrument endpoints with latency tracking",
        ),
        Check(
            "Quality metrics",
            test.get("quality_metrics", {}).get("enabled", False) or discovered_quality,
            (
                "LLM judge scoring"
                if (
                    test.get("quality_metrics", {}).get("enabled", False)
                    or discovered_quality
                )
                else "No quality measurement"
            ),
            severity="critical",
            action="Implement judge-LLM scoring on sample of responses",
        ),
        Check(
            "Eval harness",
            test.get("eval_harness", {}).get("enabled", False)
            or discovered_eval_harness,
            (
                "Automated evals"
                if (
                    test.get("eval_harness", {}).get("enabled", False)
                    or discovered_eval_harness
                )
                else "No eval framework"
            ),
            severity="critical",
            action="Create test cases with expected outputs, run against agent",
        ),
        Check(
            "CI/CD pipeline",
            test.get("ci_cd", {}).get("enabled", False) or discovered_ci,
            (
                f"{test.get('ci_cd', {}).get('provider', 'N/A')}"
                if (test.get("ci_cd", {}).get("enabled", False) or discovered_ci)
                else "No CI/CD"
            ),
            severity="warning",
            action="Set up GitHub Actions to run tests on push",
        ),
        Check(
            "Coverage gate enforced in CI",
            discovered_cov_gate,
            (
                "Detected --cov-fail-under"
                if discovered_cov_gate
                else "No fail-under gate detected"
            ),
            severity="warning",
            action="Add --cov-fail-under to CI pytest command",
        ),
        Check(
            "Feedback loop",
            test.get("iterate_and_improve", {}).get("feedback_loop", False)
            or discovered_feedback_loop,
            (
                "Connected"
                if (
                    test.get("iterate_and_improve", {}).get("feedback_loop", False)
                    or discovered_feedback_loop
                )
                else "User feedback not connected to evals"
            ),
            severity="warning",
        ),
    ]

    report.checks = checks
    passed = sum(1 for c in checks if c.passed)
    report.score = min(10, round(passed / len(checks) * 10))
    report.compute_status()
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────


def _discover_code_facts(config_path: str) -> dict:
    """Collect lightweight codebase facts used by --check-code."""
    config_file = Path(config_path).resolve()
    repo_root = config_file.parent
    backend_dir = repo_root / "backend"
    tests_dir = backend_dir / "tests"

    test_files = []
    if tests_dir.exists():
        test_files = list(tests_dir.glob("test_*.py"))

    latency_present = False
    agent_route = backend_dir / "app" / "routes" / "agent.py"
    if agent_route.exists():
        try:
            content = agent_route.read_text(encoding="utf-8")
            latency_present = (
                "latency_metrics" in content and "_record_latency_metric" in content
            )
        except Exception:
            latency_present = False

    eval_harness_present = False
    evals_dir = backend_dir / "evals"
    eval_script = evals_dir / "run_eval_harness.py"
    eval_cases = evals_dir / "test_cases.json"
    if eval_script.exists() and eval_cases.exists():
        try:
            import json as _json

            data = _json.loads(eval_cases.read_text(encoding="utf-8"))
            cases = data.get("cases", []) if isinstance(data, dict) else []
            eval_harness_present = len(cases) > 0
        except Exception:
            eval_harness_present = True

    quality_scoring_present = False
    quality_module = backend_dir / "app" / "agent" / "quality.py"
    agent_route = backend_dir / "app" / "routes" / "agent.py"
    if quality_module.exists() and agent_route.exists():
        try:
            quality_content = quality_module.read_text(encoding="utf-8")
            route_content = agent_route.read_text(encoding="utf-8")
            quality_scoring_present = (
                "score_response_quality" in quality_content
                and "response_quality" in quality_content
                and "_schedule_quality_scoring" in route_content
            )
        except Exception:
            quality_scoring_present = False

    feedback_mechanism_present = False
    feedback_loop_present = False
    history_route = backend_dir / "app" / "routes" / "history.py"
    memory_module = backend_dir / "app" / "agent" / "memory.py"
    if history_route.exists():
        try:
            history_content = history_route.read_text(encoding="utf-8")
            feedback_mechanism_present = (
                "/{task_id}/feedback" in history_content
                and "task_feedback" in history_content
            )
            feedback_loop_present = (
                "save_feedback_learning" in history_content
                and "task_feedback" in history_content
            )
        except Exception:
            feedback_mechanism_present = False
            feedback_loop_present = False

    if feedback_loop_present and memory_module.exists():
        try:
            memory_content = memory_module.read_text(encoding="utf-8")
            feedback_loop_present = "def save_feedback_learning" in memory_content
        except Exception:
            feedback_loop_present = False

    memory_temporal_search_present = False
    working_memory_present = False
    memory_decay_present = False
    memory_module = backend_dir / "app" / "agent" / "memory.py"
    orchestrator_module = backend_dir / "app" / "agent" / "orchestrator.py"
    if memory_module.exists():
        try:
            memory_content = memory_module.read_text(encoding="utf-8")
            memory_temporal_search_present = (
                "def search_by_time_range" in memory_content
            )
            memory_decay_present = "def apply_relevance_decay" in memory_content
        except Exception:
            memory_temporal_search_present = False
            memory_decay_present = False
    if orchestrator_module.exists():
        try:
            orchestrator_content = orchestrator_module.read_text(encoding="utf-8")
            working_memory_present = (
                "working_memory" in orchestrator_content
                and "planned_tool_call" in orchestrator_content
            )
        except Exception:
            working_memory_present = False

    ci_pipeline_present = False
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.exists():
        for workflow_file in workflows_dir.glob("*.yml"):
            try:
                content = workflow_file.read_text(encoding="utf-8")
            except Exception:
                continue

            has_push_trigger = "on:" in content and "push:" in content
            has_test_signal = ("pytest" in content) or (
                "backend tests" in content.lower()
            )
            if has_push_trigger and has_test_signal:
                ci_pipeline_present = True
                break

    mcp_integration_present = False
    agent_as_tool_present = False
    scheduled_triggers_present = False
    event_triggers_present = False
    message_queue_present = False
    agent2agent_present = False
    circuit_breaker_present = False
    dead_letter_present = False

    mcp_module = backend_dir / "app" / "tools" / "mcp_client.py"
    mcp_hub_module = backend_dir / "app" / "tools" / "mcp_hub.py"
    sub_agent_module = backend_dir / "app" / "agent" / "sub_agent.py"
    runtime_module = backend_dir / "app" / "agent" / "orchestration_runtime.py"
    orchestrator_module = backend_dir / "app" / "agent" / "orchestrator.py"
    main_module = backend_dir / "app" / "main.py"
    agent_route_module = backend_dir / "app" / "routes" / "agent.py"

    if mcp_module.exists():
        try:
            mcp_content = mcp_module.read_text(encoding="utf-8")
            mcp_integration_present = (
                "class MCPClient" in mcp_content and "call_tool" in mcp_content
            )
        except Exception:
            mcp_integration_present = False
    if mcp_hub_module.exists():
        try:
            hub_content = mcp_hub_module.read_text(encoding="utf-8")
            mcp_integration_present = mcp_integration_present or (
                "class McpConnectionHub" in hub_content
                and "register_hub_servers_into_registry" in hub_content
            )
        except Exception:
            pass

    if sub_agent_module.exists():
        try:
            sub_content = sub_agent_module.read_text(encoding="utf-8")
            agent_as_tool_present = (
                "class SubAgentRunner" in sub_content and "run_sub_agent" in sub_content
            )
        except Exception:
            agent_as_tool_present = False

    if runtime_module.exists():
        try:
            runtime_content = runtime_module.read_text(encoding="utf-8")
            scheduled_triggers_present = (
                "add_interval_job" in runtime_content
                and "_scheduler_loop" in runtime_content
            )
            event_triggers_present = (
                "register_event_handler" in runtime_content
                and "emit_event" in runtime_content
            )
            message_queue_present = "enqueue_task" in runtime_content and (
                "asyncio.Queue" in runtime_content
                or "redis.from_url" in runtime_content
            )
            dead_letter_present = (
                "INSERT INTO failed_tasks" in runtime_content
                and "_dead_letter_enabled" in runtime_content
            )
        except Exception:
            scheduled_triggers_present = False
            event_triggers_present = False
            message_queue_present = False
            dead_letter_present = False

    if orchestrator_module.exists():
        try:
            orch_content = orchestrator_module.read_text(encoding="utf-8")
            agent2agent_present = "def run_sub_agent" in orch_content
            circuit_breaker_present = (
                "_is_circuit_open" in orch_content
                and "_record_circuit_failure" in orch_content
            )
        except Exception:
            agent2agent_present = False
            circuit_breaker_present = False

    if main_module.exists():
        try:
            main_content = main_module.read_text(encoding="utf-8")
            # Runtime must be wired into app lifecycle to count as active.
            runtime_wired = (
                "OrchestrationRuntime" in main_content
                and "orchestration_runtime" in main_content
            )
            scheduled_triggers_present = scheduled_triggers_present and runtime_wired
            event_triggers_present = event_triggers_present and runtime_wired
            message_queue_present = message_queue_present and runtime_wired
        except Exception:
            pass

    if agent_route_module.exists():
        try:
            route_content = agent_route_module.read_text(encoding="utf-8")
            message_queue_present = (
                message_queue_present and "/enqueue" in route_content
            )
        except Exception:
            pass

    slack_discord_bot_present = False
    integrations_module = backend_dir / "app" / "integrations" / "slack_discord_bot.py"
    integrations_route = backend_dir / "app" / "routes" / "integrations.py"
    if integrations_module.exists() and integrations_route.exists():
        try:
            module_content = integrations_module.read_text(encoding="utf-8")
            route_content = integrations_route.read_text(encoding="utf-8")
            slack_discord_bot_present = (
                "class SlackDiscordBot" in module_content
                and "/slack/webhook" in route_content
                and "/discord/webhook" in route_content
            )
        except Exception:
            slack_discord_bot_present = False

    coverage_gate_present = False
    if workflows_dir.exists():
        for workflow_file in workflows_dir.glob("*.yml"):
            try:
                content = workflow_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if "--cov-fail-under" in content:
                coverage_gate_present = True
                break

    return {
        "pytest_test_files": len(test_files),
        "pytest_config_present": (
            (repo_root / "pytest.ini").exists() or (backend_dir / "pytest.ini").exists()
        ),
        "latency_instrumentation_present": latency_present,
        "eval_harness_present": eval_harness_present,
        "quality_scoring_present": quality_scoring_present,
        "feedback_mechanism_present": feedback_mechanism_present,
        "feedback_loop_present": feedback_loop_present,
        "memory_temporal_search_present": memory_temporal_search_present,
        "working_memory_present": working_memory_present,
        "memory_decay_present": memory_decay_present,
        "ci_pipeline_present": ci_pipeline_present,
        "mcp_integration_present": mcp_integration_present,
        "agent_as_tool_present": agent_as_tool_present,
        "scheduled_triggers_present": scheduled_triggers_present,
        "event_triggers_present": event_triggers_present,
        "message_queue_present": message_queue_present,
        "agent2agent_present": agent2agent_present,
        "circuit_breaker_present": circuit_breaker_present,
        "slack_discord_bot_present": slack_discord_bot_present,
        "dead_letter_present": dead_letter_present,
        "coverage_gate_present": coverage_gate_present,
    }


def generate_report(config_path: str, check_code: bool = False) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    if check_code:
        cfg["__code_facts__"] = _discover_code_facts(config_path)

    validators = [
        validate_pillar_1,
        validate_pillar_2,
        validate_pillar_3,
        validate_pillar_4,
        validate_pillar_5,
        validate_pillar_6,
        validate_pillar_7,
        validate_pillar_8,
    ]

    pillars = [v(cfg) for v in validators]
    total_score = sum(p.score for p in pillars)
    max_score = sum(p.max_score for p in pillars)
    overall_percent = round(total_score / max_score * 100)

    # Collect critical actions
    critical_actions = []
    warning_actions = []
    for p in pillars:
        for c in p.checks:
            if not c.passed and c.action:
                item = f"[Pillar {p.number}] {c.action}"
                if c.severity == "critical":
                    critical_actions.append(item)
                elif c.severity == "warning":
                    warning_actions.append(item)

    return {
        "pillars": pillars,
        "total_score": total_score,
        "max_score": max_score,
        "overall_percent": overall_percent,
        "critical_actions": critical_actions,
        "warning_actions": warning_actions,
    }


def print_report(report: dict):
    print("=" * 70)
    print("  AGENT 8-PILLAR COMPLIANCE REPORT")
    print("=" * 70)
    print()

    for p in report["pillars"]:
        bar = "█" * p.score + "░" * (10 - p.score)
        print(f"  {p.number}. {p.name:<30} [{bar}] {p.score}/10  {p.status}")

    print()
    print(
        f"  Overall: {report['total_score']}/{report['max_score']} ({report['overall_percent']}%)"
    )
    print()

    if report["critical_actions"]:
        print("─" * 70)
        print("  🔴 CRITICAL ACTIONS (fix these first)")
        print("─" * 70)
        for a in report["critical_actions"]:
            print(f"    • {a}")
        print()

    if report["warning_actions"]:
        print("─" * 70)
        print("  ⚠️  RECOMMENDED IMPROVEMENTS")
        print("─" * 70)
        for a in report["warning_actions"]:
            print(f"    • {a}")
        print()

    # Detailed checks
    print("─" * 70)
    print("  DETAILED CHECKS")
    print("─" * 70)
    for p in report["pillars"]:
        print(f"\n  Pillar {p.number}: {p.name}")
        for c in p.checks:
            icon = "✓" if c.passed else "✗"
            print(f"    {icon} {c.name}: {c.detail}")
    print()


def print_json_report(report: dict):
    output = {
        "total_score": report["total_score"],
        "max_score": report["max_score"],
        "overall_percent": report["overall_percent"],
        "pillars": [
            {
                "number": p.number,
                "name": p.name,
                "score": p.score,
                "status": p.status,
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "detail": c.detail,
                        "severity": c.severity,
                        "action": c.action,
                    }
                    for c in p.checks
                ],
            }
            for p in report["pillars"]
        ],
        "critical_actions": report["critical_actions"],
        "warning_actions": report["warning_actions"],
    }
    print(json.dumps(output, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Validate agent system against 8-pillar framework"
    )
    parser.add_argument(
        "--config", default="agent_pillars.yaml", help="Path to YAML config"
    )
    parser.add_argument(
        "--check-code", action="store_true", help="Also scan codebase for compliance"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--ci", action="store_true", help="Exit 1 if score below threshold"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=60,
        help="Minimum score %% for CI pass (default: 60)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Config not found: {args.config}")
        print("Create agent_pillars.yaml from the template first.")
        sys.exit(1)

    report = generate_report(args.config, check_code=args.check_code)

    if args.json:
        print_json_report(report)
    else:
        print_report(report)

    if args.ci and report["overall_percent"] < args.threshold:
        print(
            f"CI FAIL: Score {report['overall_percent']}% < threshold {args.threshold}%"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
