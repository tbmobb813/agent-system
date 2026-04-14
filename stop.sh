#!/usr/bin/env bash
# Stop all agent system services.

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/logs"

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[stop]${NC} $*"; }

stop_pid() {
    local name="$1"
    local pidfile="$LOG_DIR/$2.pid"
    if [ -f "$pidfile" ]; then
        PID=$(cat "$pidfile")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" && log "$name stopped (pid $PID)"
        else
            log "$name was not running"
        fi
        rm -f "$pidfile"
    fi
}

stop_pid "Backend"      backend
stop_pid "Frontend"     frontend
stop_pid "Telegram bot" telegram

# Kill any lingering processes on known ports
fuser -k 8000/tcp 2>/dev/null && log "Cleared port 8000" || true
fuser -k 3003/tcp 2>/dev/null && log "Cleared port 3003" || true

log "All services stopped"
