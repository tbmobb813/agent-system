#!/usr/bin/env bash
# Run the same checks as .github/workflows/ci.yml (backend, frontend, telegram, migrations).
# Usage: from repo root —  ./scripts/run-ci-checks.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export BACKEND_API_KEY="${BACKEND_API_KEY:-sk-agent-local-dev}"
export OPENROUTER_BUDGET_MONTHLY="${OPENROUTER_BUDGET_MONTHLY:-30.0}"

PYTEST="${ROOT}/backend/.venv/bin/pytest"
if [[ ! -x "$PYTEST" ]]; then
  echo "Missing $PYTEST — create the backend venv: cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

echo "== Backend pytest =="
"$PYTEST" -q

echo "== Frontend lint =="
(cd "$ROOT/frontend" && NEXT_TELEMETRY_DISABLED=1 npm run lint)

echo "== Frontend build =="
(cd "$ROOT/frontend" && NEXT_TELEMETRY_DISABLED=1 BACKEND_URL=http://127.0.0.1:8000 npm run build)

echo "== Frontend Playwright (install browsers if needed) =="
(cd "$ROOT/frontend" && npx playwright install chromium && CI=true NEXT_TELEMETRY_DISABLED=1 npm run test:e2e)

echo "== Telegram bot (syntax) =="
python3 -m py_compile "$ROOT/telegram-bot/bot.py"

echo "== Supabase migrations =="
count=$(find "$ROOT/supabase/migrations" -name '*.sql' 2>/dev/null | wc -l)
if [[ "$count" -eq 0 ]]; then echo "No SQL migration files found" >&2; exit 1; fi
for f in "$ROOT"/supabase/migrations/*.sql; do
  if [[ ! -s "$f" ]]; then echo "Empty migration: $f" >&2; exit 1; fi
done

echo "All checks passed."
