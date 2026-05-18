#!/usr/bin/env bash
# Stop all agent system services.

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[stop]${NC} $*"; }

# Backend — managed by PM2
if command -v pm2 >/dev/null 2>&1 && pm2 describe agent-backend >/dev/null 2>&1; then
    pm2 stop agent-backend
    log "Backend stopped (PM2)"
else
    fuser -k 8000/tcp 2>/dev/null && log "Backend stopped (port 8000 cleared)" || log "Backend was not running"
fi

# Frontend — managed by PM2
if command -v pm2 >/dev/null 2>&1 && pm2 describe agent-frontend >/dev/null 2>&1; then
    pm2 stop agent-frontend
    log "Frontend stopped (PM2)"
else
    fuser -k 3003/tcp 2>/dev/null && log "Frontend stopped (port 3003 cleared)" || log "Frontend was not running"
fi

# Telegram bot — managed by systemd
if systemctl is-enabled agent-telegram >/dev/null 2>&1; then
    systemctl stop agent-telegram
    log "Telegram bot stopped (systemd)"
else
    pkill -f "bot.py" 2>/dev/null && log "Telegram bot stopped" || log "Telegram bot was not running"
fi

log "All services stopped"
