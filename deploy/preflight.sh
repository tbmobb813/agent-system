#!/usr/bin/env bash
# =============================================================================
# preflight.sh — Deployment readiness checks for VPS
# Usage:
#   bash deploy/preflight.sh
#   bash deploy/preflight.sh --with-tests
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

WITH_TESTS=0
if [[ "${1:-}" == "--with-tests" ]]; then
  WITH_TESTS=1
fi

err() { echo "[preflight][error] $*" >&2; exit 1; }
warn() { echo "[preflight][warn]  $*"; }
ok() { echo "[preflight][ok]    $*"; }
# Use backend venv Python if available, otherwise fall back to system python3
PYTHON_BIN="python3"
if [[ -f "backend/.venv/bin/python" ]]; then
  PYTHON_BIN="backend/.venv/bin/python"
elif [[ -f "backend/venv/bin/python" ]]; then
  PYTHON_BIN="backend/venv/bin/python"
fi


[[ -f ".env" ]] || err ".env is missing (copy from .env.example and fill secrets)"

required_vars=(
  "OPENROUTER_API_KEY"
  "BACKEND_API_KEY"
  "DATABASE_URL"
)

for key in "${required_vars[@]}"; do
  if ! grep -E -q "^${key}=" .env; then
    err "Missing required env var: ${key}"
  fi
  val="$(grep -E "^${key}=" .env | tail -1 | cut -d'=' -f2-)"
  [[ -n "${val// }" ]] || err "Env var ${key} is empty"
done
ok "Required env vars present"

if ! grep -E -q '^ENVIRONMENT=production$' .env; then
  warn "ENVIRONMENT is not set to production in .env"
fi

if grep -E -q '^E2B_API_KEY=$' .env || ! grep -E -q '^E2B_API_KEY=' .env; then
  warn "E2B_API_KEY not set (code_execution tool will stay disabled)"
fi

if grep -E -q '^REDIS_URL=' .env; then
  ok "REDIS_URL configured"
else
  warn "REDIS_URL not set (queue falls back to in-process asyncio)"
fi

ok "Running pillar validator with code scan"
$PYTHON_BIN agent_pillar_validator.py --check-code >/dev/null
ok "Validator passed"

ok "Running eval harness gate"
$PYTHON_BIN backend/evals/run_eval_harness.py --ci --min-score 80 >/dev/null
ok "Eval harness passed"

if [[ $WITH_TESTS -eq 1 ]]; then
  ok "Running backend pytest + coverage gate"
  (
    cd backend
    PYTHONPATH=. $PYTHON_BIN -m pytest --cov=app --cov-fail-under=55 -q >/dev/null
  )
  ok "Backend tests passed"
else
  warn "Skipped full pytest run (pass --with-tests to include it)"
fi

ok "Preflight checks complete"
