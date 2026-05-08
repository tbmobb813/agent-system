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
| `/agent/enqueue` | POST | Queue deferred task (background worker) |
| `/agent/tools/health` | GET | Tool + MCP readiness snapshot |
| `/agent/stats` | GET | p50/p95/p99 latency by endpoint (`latency_metrics` table) |
| `/agent/schedules` | POST | Create cron schedule (prompt run on schedule) |
| `/agent/schedules` | GET | List schedules (optional `?user_id=`) |
| `/agent/schedules/{id}` | DELETE | Delete schedule (optional `?user_id=`) |
| `/agent/workflows/{name}/run` | POST | Run YAML workflow from `backend/data/workflows/{name}.yaml` |
| `/history` | GET | Paginated task history |
| `/history/{id}` | GET | Single task detail |
| `/history/{id}` | DELETE | Delete a task |
| `/settings` | GET | Get current settings |
| `/settings` | POST | Update settings |
| `/memory` | GET | List memory entries |
| `/memory/search` | GET | Search memory |
| `/memory/range` | GET | Memories in time window (`start`, `end` ISO8601) |
| `/memory` | POST | Add memory entry |
| `/memory/{id}` | DELETE | Delete memory entry |
| `/conversations` | GET | List conversations |
| `/conversations/{id}` | GET | Get conversation |
| `/conversations/{id}` | DELETE | Delete conversation |
| `/history/{task_id}/feedback` | POST | Thumbs / feedback for a task |

Workflow run body is optional JSON (`user_id`). Example:

`POST /agent/workflows/example/run` with `{}`

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

Migrations are in `supabase/migrations/`.

**Option A — Supabase CLI (recommended if the project is linked)**

The CLI is invoked via **`npx`** unless you installed `supabase` globally (`npm i -g supabase`).

```bash
# One-time: link your project (ref = Dashboard → Project Settings → General → Reference ID)
npx supabase link --project-ref <YOUR_PROJECT_REF>

npx supabase db push
```

**Option B — Python helper** (uses `DATABASE_URL` from `backend/.env`; needs a reachable Postgres — fix URL if you see pooler “tenant not found” errors)

```bash
cd /home/nixstation-remote/agent-system
python3 scripts/apply_recent_migrations.py
```

If the project was **paused** in the Supabase dashboard, unpause and wait until the database is healthy before pushing or running the script above (paused projects often show pooler / tenant resolution errors).

**Option C — Dashboard**

Open Supabase → SQL Editor → paste and run the contents of:

- `supabase/migrations/016_scheduled_tasks.sql`
- `supabase/migrations/017_latency_metrics.sql`

Recent additions include `scheduled_tasks`, `latency_metrics`, and related tables — apply before using `/agent/schedules` or `/agent/stats` with persisted metrics.

**If `db push` fails with “already exists”:** your remote DB was likely created earlier without matching migration history. Options: (1) run `npx supabase migration list` then `npx supabase migration repair <version> --status applied` for migrations that are already reflected in the DB; (2) pull latest repo — `001_initial_schema.sql` uses `CREATE INDEX IF NOT EXISTS` so re-applying `001` is safe for indexes; (3) apply only new files via **Option C** (SQL Editor) or `scripts/apply_recent_migrations.py`.

---

## Tests & eval harness

From repo root:

```bash
cd backend
source venv/bin/activate   # if you use a venv
pip install -r requirements.txt
BACKEND_API_KEY=sk-agent-local-dev OPENROUTER_BUDGET_MONTHLY=30 pytest --cov=app --cov-fail-under=55 -q
```

Router / pattern eval cases (no live agent):

```bash
# From repo root
python3 backend/evals/run_eval_harness.py
python3 backend/evals/run_eval_harness.py --ci --min-score 80

# From backend/ directory
python3 evals/run_eval_harness.py --ci --min-score 80
```

Pillar compliance (optional):

```bash
python3 agent_pillar_validator.py --check-code
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
| `REDIS_URL` | Optional — durable deferred queue when `message_queue.provider` is `redis` |
| `OPENAI_API_KEY` | OpenAI key for embeddings (optional) |
| `ALERT_WEBHOOK_URL` | Webhook for budget alerts (optional) |
