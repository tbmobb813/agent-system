#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Pull latest code and restart services
# Run after every git push to deploy updates.
# Usage: bash deploy/deploy.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DEPLOY_ENV_FILE="$REPO_DIR/deploy/.env.deploy"
ALLOWED_DEPLOY_ENV_KEYS=("MONITOR_BASE_URL" "ALERT_WEBHOOK_URL")

is_allowed_deploy_env_key() {
	local key="$1"
	local allowed_key
	for allowed_key in "${ALLOWED_DEPLOY_ENV_KEYS[@]}"; do
		if [[ "$key" == "$allowed_key" ]]; then
			return 0
		fi
	done
	return 1
}

trim_whitespace() {
	local value="$1"
	local extglob_was_enabled=0
	if shopt -q extglob; then
		extglob_was_enabled=1
	fi
	shopt -s extglob
	value="${value##+([[:space:]])}"
	value="${value%%+([[:space:]])}"
	if [[ "$extglob_was_enabled" -eq 0 ]]; then
		shopt -u extglob
	fi
	printf '%s' "$value"
}

if [[ -f "$DEPLOY_ENV_FILE" ]]; then
	echo "==> Loading deploy env from deploy/.env.deploy"
	line_number=0
	while IFS= read -r line || [[ -n "$line" ]]; do
		((line_number += 1))
		[[ -z "$(trim_whitespace "$line")" || "$line" =~ ^[[:space:]]*# ]] && continue
		if [[ "$line" =~ ^[[:space:]]*([A-Za-z][A-Za-z0-9_]*)[[:space:]]*=(.*)$ ]]; then
			key="${BASH_REMATCH[1]}"
			if ! is_allowed_deploy_env_key "$key"; then
				echo "[deploy][warn] Ignoring unsupported key '$key' on line $line_number in deploy/.env.deploy" >&2
				continue
			fi
			value="$(trim_whitespace "${BASH_REMATCH[2]}")"
			if [[ "$value" =~ ^\"(.*)\"$ ]]; then
				value="${BASH_REMATCH[1]}"
			elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
				value="${BASH_REMATCH[1]}"
			fi
			export "$key=$value"
		else
			echo "[deploy][warn] Ignoring invalid line $line_number in deploy/.env.deploy" >&2
		fi
	done < "$DEPLOY_ENV_FILE"
fi

echo "==> Pulling latest code"
git pull origin main

echo "==> Backend — install/update dependencies"
cd "$REPO_DIR/backend"
./venv/bin/pip install -r requirements.txt -q

echo "==> Frontend — install dependencies"
cd "$REPO_DIR/frontend"
npm ci --prefer-offline

echo "==> Frontend — build"
npm run build

echo "==> Copy static assets to standalone output"
# next/standalone doesn't copy public/ or .next/static/ automatically
cp -r public .next/standalone/public 2>/dev/null || true
cp -r .next/static .next/standalone/.next/static 2>/dev/null || true
echo "==> Running deployment preflight checks"
bash "$REPO_DIR/deploy/preflight.sh"


echo "==> Restarting services"
pm2 restart all

echo "==> Monitoring smoke checks"
MONITOR_BASE_URL="${MONITOR_BASE_URL:-https://agent.techtrendwire.com}"
for attempt in 1 2 3; do
	if ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}" bash "$REPO_DIR/deploy/monitoring-smoke.sh" --base-url "$MONITOR_BASE_URL"; then
		echo "==> Monitoring checks passed"
		break
	fi
	if [[ "$attempt" -eq 3 ]]; then
		echo "[deploy][error] Monitoring checks failed after 3 attempts" >&2
		exit 1
	fi
	echo "[deploy][warn] Monitoring checks failed (attempt $attempt/3), retrying..."
	sleep 5
done

echo "==> Done. Check logs with: pm2 logs"
