#!/usr/bin/env python3
"""
Evaluation harness for agent-system.

Initial scope:
- Router behavior checks (query -> expected tier)

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
    print(f"  Score: {score:.1f}% ({sum(1 for r in results if r.passed)}/{len(results)})")


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
    parser.add_argument("--ci", action="store_true", help="Exit 1 if score is below threshold")
    parser.add_argument("--min-score", type=float, default=80.0, help="CI minimum score percentage")
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
