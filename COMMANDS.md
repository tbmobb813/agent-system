# Agent System — Command Reference

## One-Word CLI (from anywhere)

| Command | Description |
|---|---|
| `agent` | Start everything |
| `agent start` | Start everything (explicit) |
| `agent stop` | Stop everything |
| `agent status` | Check what's running |
| `agent logs` | Tail backend logs |
| `agent logs frontend` | Tail frontend logs |
| `agent logs telegram` | Tail Telegram bot logs |

---

## Web UI

Open in browser: **http://localhost:3003**

| Page | URL |
|---|---|
| Agent | http://localhost:3003/agent |
| History | http://localhost:3003/history |
| Costs | http://localhost:3003/costs |
| Settings | http://localhost:3003/settings |

---

## Backend API

Base URL: **http://localhost:8000**

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check (no auth required) |
| `/status/costs` | GET | Budget and spending status |
| `/agent/run` | POST | Run agent (sync) |
| `/agent/stream` | POST | Run agent (streaming SSE) |
| `/agent/stop` | POST | Cancel a running task |
| `/agent/tools` | GET | List available tools |
| `/agent/models` | GET | List models and routing strategy |
| `/history` | GET | Paginated task history |
| `/history/{id}` | GET | Single task detail |
| `/history/{id}` | DELETE | Delete a task |
| `/settings` | GET | Get current settings |
| `/settings` | POST | Update settings |
| `/memory` | GET | List memory entries |
| `/memory/search` | GET | Search memory |
| `/memory` | POST | Add memory entry |
| `/memory/{id}` | DELETE | Delete memory entry |
| `/conversations` | GET | List conversations |
| `/conversations/{id}` | GET | Get conversation |
| `/conversations/{id}` | DELETE | Delete conversation |

API docs (interactive): **http://localhost:8000/docs**

---

## Telegram Bot

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/new` | Start a new conversation |
| `/help` | Show available commands |
| Any message | Send to agent |

---

## Docker / SearXNG

| Command | Description |
|---|---|
| `docker start searxng` | Start SearXNG (if stopped) |
| `docker stop searxng` | Stop SearXNG |
| `docker ps` | List running containers |
| `docker logs searxng` | View SearXNG logs |

SearXNG UI: **http://localhost:8888**

---

## Database (Supabase)

Migrations are in `supabase/migrations/`. Apply via Supabase dashboard or:

```bash
supabase db push
```

---

## Development

```bash
# Backend only (with hot reload)
cd /home/nixstation-remote/agent-system/backend
source venv/bin/activate
uvicorn app.main:app --reload

# Frontend only
cd /home/nixstation-remote/agent-system/frontend
npm run dev

# Telegram bot only
cd /home/nixstation-remote/agent-system/telegram-bot
source venv/bin/activate
python3 bot.py

# Install new backend dependency
cd /home/nixstation-remote/agent-system/backend
source venv/bin/activate
pip install <package>
pip freeze > requirements.txt

# Install new frontend dependency
cd /home/nixstation-remote/agent-system/frontend
npm install <package>
```

---

## Production (VPS)

```bash
# Build and start all services
docker-compose -f docker-compose.prod.yml up -d --build

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend

# Stop all
docker-compose -f docker-compose.prod.yml down

# Restart a single service
docker-compose -f docker-compose.prod.yml restart backend
```

---

## Log Files (local dev)

Located in `/home/nixstation-remote/agent-system/logs/`

| File | Service |
|---|---|
| `backend.log` | FastAPI backend |
| `frontend.log` | Next.js frontend |
| `telegram.log` | Telegram bot |
| `backend.pid` | Backend process ID |
| `frontend.pid` | Frontend process ID |
| `telegram.pid` | Telegram bot process ID |

---

## Environment Variables

Config file: `/home/nixstation-remote/agent-system/backend/.env`

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter API key (required) |
| `OPENROUTER_BUDGET_MONTHLY` | Monthly budget in USD (default: 30.0) |
| `BACKEND_API_KEY` | Master API key for web UI auth |
| `DATABASE_URL` | PostgreSQL connection string |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (for budget alerts) |
| `SEARXNG_URL` | SearXNG instance URL (default: http://localhost:8888) |
| `BRAVE_SEARCH_API_KEY` | Brave Search fallback key (optional) |
| `E2B_API_KEY` | E2B sandbox key for code execution |
| `OPENAI_API_KEY` | OpenAI key for embeddings (optional) |
| `ALERT_WEBHOOK_URL` | Webhook for budget alerts (optional) |
