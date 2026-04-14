#!/usr/bin/env bash
# Start the full agent system: backend, frontend, telegram bot, and SearXNG.
# Run from the agent-system root directory.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
BOT="$ROOT/telegram-bot"
LOG_DIR="$ROOT/logs"

mkdir -p "$LOG_DIR"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[start]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
die()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── SearXNG ───────────────────────────────────────────────────────────────────
log "Checking SearXNG..."
if docker ps --filter "name=searxng" --filter "status=running" --format "{{.Names}}" | grep -q searxng; then
    log "SearXNG already running"
elif docker ps -a --filter "name=searxng" --format "{{.Names}}" | grep -q searxng; then
    log "Starting existing SearXNG container..."
    docker start searxng
else
    log "Creating SearXNG container..."
    docker run -d -p 8888:8080 --name searxng searxng/searxng
fi

# ── Backend ───────────────────────────────────────────────────────────────────
log "Starting backend..."
if [ ! -d "$BACKEND/venv" ]; then
    warn "venv not found — creating it now..."
    python3 -m venv "$BACKEND/venv"
    "$BACKEND/venv/bin/pip" install -q --upgrade pip
    "$BACKEND/venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

(cd "$BACKEND" && venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --reload) \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$LOG_DIR/backend.pid"
log "Backend started (pid $BACKEND_PID) — logs: logs/backend.log"

# Wait for backend to be ready
log "Waiting for backend to be ready..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log "Backend is ready"
        break
    fi
    sleep 1
    if [ "$i" -eq 20 ]; then
        warn "Backend did not become ready in 20s — check logs/backend.log"
    fi
done

# ── Frontend ──────────────────────────────────────────────────────────────────
log "Starting frontend..."
if [ ! -d "$FRONTEND/node_modules" ]; then
    warn "node_modules not found — running npm install..."
    (cd "$FRONTEND" && npm install --silent)
fi

(cd "$FRONTEND" && PORT=3003 npm run dev) \
    > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$LOG_DIR/frontend.pid"
log "Frontend started (pid $FRONTEND_PID) — logs: logs/frontend.log"

# ── Telegram Bot ──────────────────────────────────────────────────────────────
log "Starting Telegram bot..."
BOT_VENV="$BOT/venv"
if [ ! -d "$BOT_VENV" ]; then
    warn "Bot venv not found — creating it now..."
    python3 -m venv "$BOT_VENV"
    "$BOT_VENV/bin/pip" install -q --upgrade pip
    "$BOT_VENV/bin/pip" install -q -r "$BOT/requirements-telegram.txt"
fi

(cd "$BOT" && venv/bin/python3 bot.py) \
    > "$LOG_DIR/telegram.log" 2>&1 &
BOT_PID=$!
echo $BOT_PID > "$LOG_DIR/telegram.pid"
log "Telegram bot started (pid $BOT_PID) — logs: logs/telegram.log"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Agent system running${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Web UI:    http://localhost:3003"
echo -e "  Backend:   http://localhost:8000"
echo -e "  SearXNG:   http://localhost:8888"
echo -e "  Logs:      $LOG_DIR/"
echo ""
echo -e "  Run ${YELLOW}./stop.sh${NC} to stop everything"
echo ""

# Keep script alive so Ctrl+C stops all services
trap './stop.sh 2>/dev/null; exit 0' INT TERM
wait
