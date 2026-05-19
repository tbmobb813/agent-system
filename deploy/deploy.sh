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
		[[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]] && continue
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
./.venv/bin/pip install -r requirements.txt -q

echo "==> Backend — install Playwright Chromium browser"
playwright_install_stderr="$(mktemp)"
if ! ./.venv/bin/playwright install chromium --with-deps 2>"$playwright_install_stderr"; then
	if ! ./.venv/bin/python -m playwright install chromium 2>>"$playwright_install_stderr"; then
		echo "[warn] Playwright browser install skipped (browser_automation will be unavailable)" >&2
		echo "[warn] Playwright install errors:" >&2
		cat "$playwright_install_stderr" >&2
	fi
fi
rm -f "$playwright_install_stderr"

echo "==> Frontend — install dependencies"
cd "$REPO_DIR/frontend"
pnpm install --frozen-lockfile

echo "==> Frontend — build"
pnpm run build

echo "==> Copy static assets to standalone output"
# next/standalone doesn't copy public/ or .next/static/ automatically
cp -r public .next/standalone/public 2>/dev/null || true
cp -r .next/static .next/standalone/.next/static 2>/dev/null || true
echo "==> Running database migrations"
cd "$REPO_DIR"
# Load DATABASE_URL from backend/.env if not already set
if [[ -z "${DATABASE_URL:-}" && -f "$REPO_DIR/backend/.env" ]]; then
	_raw="$(grep -E '^DATABASE_URL=' "$REPO_DIR/backend/.env" | head -1 | cut -d'=' -f2-)"
	# Strip surrounding single or double quotes
	if [[ "$_raw" =~ ^\"(.*)\"$ ]]; then
		_raw="${BASH_REMATCH[1]}"
	elif [[ "$_raw" =~ ^\'(.*)\'$ ]]; then
		_raw="${BASH_REMATCH[1]}"
	fi
	DATABASE_URL="$_raw"
	export DATABASE_URL
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
	echo "[deploy][warn] DATABASE_URL not set — skipping migrations" >&2
else
	# Ensure migration tracking table exists so each file runs at most once
	psql "$DATABASE_URL" --set=ON_ERROR_STOP=1 --quiet -c "
		CREATE TABLE IF NOT EXISTS schema_migrations (
			filename TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
	"
	for migration_file in "$REPO_DIR"/supabase/migrations/*.sql; do
		filename="$(basename "$migration_file")"
		applied="$(psql "$DATABASE_URL" --set=ON_ERROR_STOP=1 --tuples-only --quiet \
			-c "SELECT 1 FROM schema_migrations WHERE filename = '$filename';" | tr -d '[:space:]')"
		if [[ "$applied" == "1" ]]; then
			echo "  skipping $filename (already applied)"
			continue
		fi
		echo "  applying $filename"
		psql "$DATABASE_URL" --set=ON_ERROR_STOP=1 -f "$migration_file" --quiet
		psql "$DATABASE_URL" --set=ON_ERROR_STOP=1 --quiet \
			-c "INSERT INTO schema_migrations (filename) VALUES ('$filename');"
	done
	echo "==> Migrations complete"
fi

echo "==> Running deployment preflight checks"
bash "$REPO_DIR/deploy/preflight.sh"


echo "==> Restarting services"
pm2 restart all --update-env

echo "==> Waiting for services to be ready..."
for _i in $(seq 1 24); do
	_backend_ok=0
	_frontend_ok=0
	curl -sf --max-time 3 http://localhost:8000/health >/dev/null 2>&1 && _backend_ok=1
	curl -sf --max-time 3 http://localhost:3003      >/dev/null 2>&1 && _frontend_ok=1
	if [[ "$_backend_ok" -eq 1 && "$_frontend_ok" -eq 1 ]]; then
		echo "  services ready after $((_i * 5))s"
		break
	fi
	if [[ "$_i" -eq 24 ]]; then
		echo "[deploy][error] Services did not become ready within 120s" >&2
		exit 1
	fi
	sleep 5
done

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
	sleep 15
done

echo "==> Done. Check logs with: pm2 logs"
