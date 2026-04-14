# Quick Start Guide - 30 Minutes to Running Agent

This is the **fastest path** from zero to a working AI agent system. Follow this exactly.

## What You'll Have at the End

✅ FastAPI backend (localhost:8000)
✅ Next.js dashboard (localhost:3000)
✅ PostgreSQL database (running locally)
✅ OpenRouter LLM routing
✅ Cost tracking with $30/month limit
✅ Real-time streaming agent execution

## Prerequisites (2 minutes)

Make sure you have:
- Docker & Docker Compose installed
- OpenRouter API key (from openrouter.ai)
- Supabase URL + API keys (from supabase.com) - **optional, use local DB for dev**

## Step 1: Clone/Download Project (1 minute)

```bash
# If you have the files, copy them to your directory
cd ~/agent-system  # or wherever you cloned/downloaded

# Or clone from git
git clone https://github.com/yourusername/agent-system.git
cd agent-system
```

## Step 2: Create Environment File (2 minutes)

```bash
cp .env.example .env
nano .env  # or open in your editor
```

Fill in these three values (rest can stay as default):

```
OPENROUTER_API_KEY=sk_0abc...  # Get from openrouter.ai
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGc...
```

For local development, you can skip Supabase and it will use local PostgreSQL.

Save file (Ctrl+X → Y → Enter if using nano).

## Step 3: Start Everything (5 minutes)

```bash
docker-compose up
```

This will:
1. Start PostgreSQL database
2. Build backend image
3. Build frontend image
4. Start all services

Wait until you see:
```
backend_1   | INFO:     Uvicorn running on http://0.0.0.0:8000
frontend_1  | ▲ Next.js 15.x
frontend_1  | ✓ Ready in 3.2s
```

## Step 4: Verify It Works (5 minutes)

Open these in your browser:

### Backend API (should see docs)
```
http://localhost:8000/docs
```

You'll see interactive API documentation with all endpoints.

### Frontend Dashboard
```
http://localhost:3000
```

You should see the AI agent dashboard.

### Health Check
```bash
curl http://localhost:8000/health
```

Should return:
```json
{
  "status": "ok",
  "timestamp": "2024-04-12T10:00:00",
  "agent_ready": true,
  "cost_tracking": true
}
```

## Step 5: Test Your First Agent Call (5 minutes)

### Method 1: Using curl

```bash
curl -X POST http://localhost:8000/agent/stream \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France? Answer in one sentence.",
    "max_iterations": 3
  }'
```

You should see a streaming response with the answer.

### Method 2: Using the Dashboard

1. Go to http://localhost:3000
2. Type a query: "Explain quantum computing briefly"
3. Click "Run Agent"
4. Watch it work in real time

### Method 3: Check Cost

```bash
curl http://localhost:8000/status/costs
```

Returns:
```json
{
  "budget": 30.0,
  "spent_month": 0.47,
  "spent_today": 0.47,
  "remaining": 29.53,
  "percent_used": 1.57,
  "status": "ok"
}
```

## What's Running

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend** | http://localhost:8000 | FastAPI + Agent |
| **API Docs** | http://localhost:8000/docs | Interactive API explorer |
| **Frontend** | http://localhost:3000 | Next.js Dashboard |
| **Database** | localhost:5432 | PostgreSQL (local) |
| **Redis** | localhost:6379 | Cache (optional) |

## View Logs

```bash
# All logs
docker-compose logs -f

# Just backend
docker-compose logs -f backend

# Just frontend
docker-compose logs -f frontend

# Database
docker-compose logs -f postgres
```

## Stop Everything

```bash
docker-compose down
```

Or gracefully:
```bash
Ctrl+C
```

## Next Steps

### Add More Tools

Tools are in `backend/app/tools/`. See `web_search.py` for example.

### Customize Models

Edit `backend/app/config.py`:

```python
DEFAULT_MODEL_SIMPLE = "deepseek/deepseek-chat"  # Cheapest (~$0.14/MTok)
DEFAULT_MODEL_BALANCED = "anthropic/claude-3.5-haiku"  # Mid ($1/MTok)
DEFAULT_MODEL_ADVANCED = "anthropic/claude-sonnet-4"  # Best ($3/MTok)
```

### Setup Telegram Bot

```bash
cd telegram-bot
python bot.py
```

Then message your bot on Telegram and ask it anything!

### Deploy to VPS

See `SETUP.md` for full production deployment guide.

## Troubleshooting

### Backend won't start

```bash
docker-compose logs backend
```

Look for error message. Common issues:
- **Database connection failed**: Check postgres is running: `docker ps`
- **Port 8000 in use**: Kill process: `sudo lsof -i :8000`
- **Out of memory**: Increase Docker memory limit

### Frontend blank page

```bash
docker-compose logs frontend
```

Check that `NEXT_PUBLIC_API_URL=http://localhost:8000` is correct in `.env`.

### Agent responds with error

Check:
1. OpenRouter API key is correct
2. Account has credit (check openrouter.ai dashboard)
3. Backend logs: `docker-compose logs backend`

### Slow responses

Could be:
- Complex query (try simpler prompt)
- Model overloaded (try different model in config)
- Network (check internet connection)

## Advanced: Use Real Supabase Instead of Local DB

If you want to use Supabase (recommended for real deployment):

1. Create Supabase project at supabase.com
2. Run migrations:
   ```bash
   # In SQL Editor on Supabase dashboard
   # Copy content of supabase/migrations/*.sql
   # Run each one
   ```
3. Get connection string from Project Settings → Database
4. Update .env:
   ```
   DATABASE_URL=your_supabase_connection_string
   ```
5. Restart: `docker-compose down && docker-compose up`

## Advanced: Add Local LLM (Ollama)

To use a local LLM instead of OpenRouter (free!):

1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama2`
3. Run: `ollama serve` (keeps running in background)
4. Edit `backend/app/config.py` to add Ollama to fallback chain
5. Restart backend: `docker-compose restart backend`

Now cheap queries will use local Ollama, expensive ones use OpenRouter.

## File Structure

```
agent-system/
├── backend/                    # FastAPI app
│   ├── app/
│   │   ├── main.py            # Main API
│   │   ├── config.py          # Settings + cost tracking
│   │   ├── models.py          # Pydantic models
│   │   ├── agent/             # Agent orchestration
│   │   ├── tools/             # Tool definitions
│   │   └── utils/             # Helpers
│   └── requirements.txt
├── frontend/                   # Next.js dashboard
│   ├── app/
│   ├── components/
│   └── package.json
├── telegram-bot/               # Telegram bot
├── supabase/
│   └── migrations/            # Database schema
├── docker-compose.yml         # Local dev stack
└── .env.example              # Template
```

## Cost Tracking Example

Every API call is tracked:

```python
# A query costs approximately:
# - Input: 500 tokens @ $3/MTok = $0.0015
# - Output: 250 tokens @ $15/MTok = $0.00375
# - Total: $0.00525 per call

# At $0.005/call average:
# - $30/month = ~6,000 calls/month
# - $1/day = ~200 calls/day
# - Free tier: 100 calls/month at $0.50
```

## Pro Tips

1. **Start cheap**: Use DeepSeek for testing ($0.14/MTok)
2. **Batch expensive work**: Group similar queries to reuse cache
3. **Monitor spending**: Check `http://localhost:8000/status/costs` daily
4. **Use streaming**: Better UX and you see progress in real time
5. **Keep context tight**: Agent works better with focused queries

## Getting Help

- **API Docs**: http://localhost:8000/docs (interactive examples)
- **Logs**: `docker-compose logs -f`
- **Database**: Use Supabase dashboard to inspect tables
- **Chat**: Ask agent directly: "How do I use this?"

---

**That's it! You now have a fully functional personal AI agent system.**

Next step: Try asking it to do something fun!

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Write a haiku about programming"
  }'
```

Enjoy! 🚀
