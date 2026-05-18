#!/usr/bin/env bash
# Launcher for Next.js standalone server.
# Sources frontend/.env.local so proxy middleware has access to BACKEND_API_KEY etc.
# Also ensures public/ and static assets are present in the standalone output.
set -a
# shellcheck source=../frontend/.env.local
source "$(dirname "$0")/../frontend/.env.local"
set +a

ROOT="$(dirname "$0")/.."
STANDALONE="$ROOT/frontend/.next/standalone/frontend"

# Next.js standalone omits public/ and .next/static — copy them if stale.
rsync -a --delete "$ROOT/frontend/public/" "$STANDALONE/public/"
rsync -a --delete "$ROOT/frontend/.next/static/" "$STANDALONE/.next/static/"

exec node "$STANDALONE/server.js"
