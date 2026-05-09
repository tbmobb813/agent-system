#!/usr/bin/env bash
# =============================================================================
# monitoring-smoke.sh — Baseline production health checks with optional alerts
# Usage:
#   bash deploy/monitoring-smoke.sh --base-url https://agent.example.com
#   ALERT_WEBHOOK_URL=https://hooks.slack.com/... bash deploy/monitoring-smoke.sh
#   bash deploy/monitoring-smoke.sh --dry-run
# =============================================================================
set -euo pipefail

BASE_URL="https://agent.techtrendwire.com"
DRY_RUN=0
TIMEOUT=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --timeout)
      TIMEOUT="${2:-10}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

report_failure() {
  local message="$1"
  echo "[monitoring][error] $message" >&2

  if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
    curl -sS -m "$TIMEOUT" -X POST "$ALERT_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":\"agent-system monitoring alert: ${message}\"}" >/dev/null || true
  fi

  exit 1
}

check_status() {
  local label="$1"
  local url="$2"
  local expected="$3"

  echo "[monitoring] checking $label -> $url"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi

  local code
  code="$(curl -sS -m "$TIMEOUT" -o /dev/null -w '%{http_code}' "$url")" || report_failure "$label request failed"

  if [[ "$code" != "$expected" ]]; then
    report_failure "$label expected HTTP $expected, got $code"
  fi
}

echo "[monitoring] base_url=$BASE_URL dry_run=$DRY_RUN"

check_status "frontend" "$BASE_URL/" "200"
check_status "backend-health" "$BASE_URL/api/backend/health" "200"

echo "[monitoring] all checks passed"
