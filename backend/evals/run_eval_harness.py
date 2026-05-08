#!/usr/bin/env python3
"""
Evaluation harness for agent-system.

Scope:
- Router behavior (query -> expected tier)
- Static text pattern checks (must_contain / must_not_contain)
- Tool trace expectations (expected_tools_called) against a recorded trace

Usage:
  python backend/evals/run_eval_harness.py
  python backend/evals/run_eval_harness.py --cases backend/evals/test_cases.json
  python backend/evals/run_eval_harness.py --json
  python backend/evals/run_eval_harness.py --ci --min-score 80
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.router import ModelRouter  # noqa: E402


@dataclass
class EvalResult:
    case_id: str
    case_type: str
    passed: bool
    expected: str
    actual: str


def _run_router_tier_case(router: ModelRouter, case: dict[str, Any]) -> EvalResult:
    case_id = str(case.get("id", "unknown"))
    query = str(case.get("input", ""))
    expected_tier = str(case.get("expected_tier", ""))
    actual_tier = router._classify(query)  # Intentional internal classifier assertion
    return EvalResult(
        case_id=case_id,
        case_type="router_tier",
        passed=(actual_tier == expected_tier),
        expected=expected_tier,
        actual=actual_tier,
    )


def _run_agent_model_case(router: ModelRouter, case: dict[str, Any]) -> EvalResult:
    """When tools are enabled, select_for_run picks agent tier unless budget forces free."""
    case_id = str(case.get("id", "unknown"))
    query = str(case.get("input", "test"))
    budget = float(case.get("budget_remaining", 30.0))
    expect = str(case.get("expect_model_tier", "agent")).strip().lower()
    if expect == "free":
        expected = router.MODELS["free"]["model"]
    else:
        expected = router.MODELS["agent"]["model"]
    actual = router.select_for_run(query, has_tools=True, budget_remaining=budget)
    return EvalResult(
        case_id=case_id,
        case_type="router_agent_model",
        passed=(actual == expected),
        expected=expected,
        actual=actual,
    )


def _run_static_text_case(case: dict[str, Any]) -> EvalResult:
    case_id = str(case.get("id", "unknown"))
    text = str(case.get("text", ""))
    must_contain = case.get("must_contain") or []
    must_not_contain = case.get("must_not_contain") or []
    failures: list[str] = []

    if isinstance(must_contain, str):
        must_contain = [must_contain]
    if isinstance(must_not_contain, str):
        must_not_contain = [must_not_contain]

    for s in must_contain:
        if str(s) not in text:
            failures.append(f"missing:{s!r}")
    for s in must_not_contain:
        if str(s) in text:
            failures.append(f"forbidden_present:{s!r}")

    passed = len(failures) == 0
    return EvalResult(
        case_id=case_id,
        case_type="static_text",
        passed=passed,
        expected=f"must_contain={must_contain!r}; must_not_contain={must_not_contain!r}",
        actual="ok" if passed else "; ".join(failures),
    )


def _run_tool_trace_case(case: dict[str, Any]) -> EvalResult:
    case_id = str(case.get("id", "unknown"))
    tools_called = case.get("tools_called") or []
    expected_tools = case.get("expected_tools_called") or []
    forbidden = case.get("forbidden_tools_called") or []

    if not isinstance(tools_called, list):
        tools_called = []
    if not isinstance(expected_tools, list):
        expected_tools = []
    if not isinstance(forbidden, list):
        forbidden = []

    tools_set = set(str(t) for t in tools_called)
    missing = [t for t in expected_tools if str(t) not in tools_set]
    bad = [t for t in forbidden if str(t) in tools_set]

    passed = not missing and not bad
    return EvalResult(
        case_id=case_id,
        case_type="tool_trace",
        passed=passed,
        expected=f"need {expected_tools!r}, forbid {forbidden!r}",
        actual=f"got {list(tools_called)!r}"
        + (f"; missing {missing!r}" if missing else "")
        + (f"; forbidden_hit {bad!r}" if bad else ""),
    )


def run_eval_cases(case_file: Path) -> tuple[list[EvalResult], float]:
    data = json.loads(case_file.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("'cases' must be a list")

    router = ModelRouter()
    results: list[EvalResult] = []

    for case in cases:
        if not isinstance(case, dict):
            continue
        case_type = case.get("type")
        if case_type == "router_tier":
            results.append(_run_router_tier_case(router, case))
            continue
        if case_type == "router_agent_model":
            results.append(_run_agent_model_case(router, case))
            continue
        if case_type == "static_text":
            results.append(_run_static_text_case(case))
            continue
        if case_type == "tool_trace":
            results.append(_run_tool_trace_case(case))
            continue

        results.append(
            EvalResult(
                case_id=str(case.get("id", "unknown")),
                case_type=str(case_type or "unknown"),
                passed=False,
                expected="supported case type",
                actual=f"unsupported case type: {case_type}",
            )
        )

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    score = (passed / total * 100.0) if total > 0 else 0.0
    return results, score


def print_human(results: list[EvalResult], score: float) -> None:
    print("=" * 70)
    print("  AGENT EVAL HARNESS REPORT")
    print("=" * 70)
    print()
    for r in results:
        icon = "PASS" if r.passed else "FAIL"
        print(f"  [{icon}] {r.case_id} ({r.case_type})")
        if not r.passed:
            print(f"         expected: {r.expected}")
            print(f"         actual:   {r.actual}")
    print()
    print(
        f"  Score: {score:.1f}% ({sum(1 for r in results if r.passed)}/{len(results)})"
    )


def print_json(results: list[EvalResult], score: float) -> None:
    payload = {
        "score": score,
        "passed": sum(1 for r in results if r.passed),
        "total": len(results),
        "results": [
            {
                "id": r.case_id,
                "type": r.case_type,
                "passed": r.passed,
                "expected": r.expected,
                "actual": r.actual,
            }
            for r in results
        ],
    }
    print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval harness test cases")
    parser.add_argument(
        "--cases",
        default=str(REPO_ROOT / "backend" / "evals" / "test_cases.json"),
        help="Path to eval test cases JSON",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--ci", action="store_true", help="Exit 1 if score is below threshold"
    )
    parser.add_argument(
        "--min-score", type=float, default=80.0, help="CI minimum score percentage"
    )
    args = parser.parse_args()

    case_file = Path(args.cases).resolve()
    if not case_file.exists():
        print(f"Case file not found: {case_file}")
        sys.exit(1)

    results, score = run_eval_cases(case_file)

    if args.json:
        print_json(results, score)
    else:
        print_human(results, score)

    if args.ci and score < args.min_score:
        print(f"CI FAIL: score {score:.1f}% < threshold {args.min_score:.1f}%")
        sys.exit(1)


if __name__ == "__main__":
    main()
