#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Pull latest code and restart services
# Run after every git push to deploy updates.
# Usage: bash deploy/deploy.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

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

echo "==> Restarting services"
pm2 restart all

echo "==> Done. Check logs with: pm2 logs"
