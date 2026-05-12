#!/usr/bin/env bash
# Launcher for Next.js standalone server.
# Sources frontend/.env.local so proxy middleware has access to BACKEND_API_KEY etc.
set -a
# shellcheck source=../frontend/.env.local
source "$(dirname "$0")/../frontend/.env.local"
set +a

exec node "$(dirname "$0")/../frontend/.next/standalone/frontend/server.js"
