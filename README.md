# Personal AI Agent System

A production-ready AI agent that runs on your VPS and is accessible via web, Telegram, and mobile. Full autonomy across research, analysis, coding, and automation tasks.

**Your cost limit: $30/month enforced at runtime.**

## What This Does

- **Research & Analysis**: Web search, document analysis, competitor intelligence
- **Code**: Write, review, debug, refactor code across languages
- **Automation**: Browser automation, file operations, API integration
- **Persistent Memory**: Learns from past interactions, remembers preferences
- **Multi-Modal Access**: Web dashboard, Telegram bot, mobile app (coming soon)
- **Real-Time Streaming**: Watch your agent think and work in real time

## Tech Stack

**Backend**: FastAPI + PydanticAI + LangGraph + OpenRouter
**Frontend**: Next.js 15 + TypeScript + TailwindCSS + Vercel AI SDK
**Database**: Supabase (PostgreSQL + pgvector)
**Mobile**: Telegram bot (native app coming soon)
**Deployment**: Docker + systemd on your VPS

## Project Structure

```
agent-system/
├── backend/              # FastAPI + agent orchestration
│   ├── app/
│   │   ├── main.py       # FastAPI app entry point
│   │   ├── config.py     # Configuration + cost limits
│   │   ├── agent/        # Agent orchestration logic
│   │   ├── tools/        # Tool definitions (search, browser, code, etc)
│   │   ├── routes/       # HTTP endpoints
│   │   ├── models/       # Pydantic models
│   │   └── utils/        # Utilities (streaming, caching, etc)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/             # Next.js dashboard
│   ├── app/
│   ├── components/
│   ├── public/
│   └── package.json
├── telegram-bot/         # Telegram bot
│   ├── bot.py
│   └── requirements.txt
├── docker-compose.yml    # Local dev environment
├── supabase/
│   ├── migrations/       # Database schema
│   └── functions/        # Edge functions (optional)
└── .env.example          # Environment template
```

## Quick Start (Local Development)

### 1. Clone and setup

```bash
git clone <repo> && cd agent-system
cp .env.example .env
```

### 2. Create Supabase project

- Go to supabase.com, create a new project
- Copy your URL and API key to `.env`
- Run migrations (see `supabase/migrations/`)

### 3. Get OpenRouter API key

- Go to openrouter.ai, sign up
- Create API key, add to `.env`
- Fund account with $30 (your monthly budget)

### 4. Run locally with Docker

```bash
docker-compose up
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# Docs: http://localhost:8000/docs
```

### 5. Deploy to VPS

See `DEPLOYMENT.md` for full guide:
- Push Docker image to registry
- Set up systemd service
- Configure Telegram bot webhook
- Monitor costs + logs

## Key Features

### 1. Multi-Model Routing

Automatically routes requests to the right model:
- **Simple queries** → DeepSeek (cheap, fast)
- **Analysis/reasoning** → Claude Sonnet
- **Complex workflows** → Claude Opus
- **Coding** → GPT-4o or local Ollama

Saves ~70% on API costs vs. single-model approach.

### 2. Cost Tracking & Limits

Every request is tracked:
- Real-time cost tracking
- Monthly budget: **$30 hard limit**
- Alerts at 80% and 95%
- Per-model spending dashboard

### 3. Persistent Context Management

- Automatic context window compaction at 75%
- Sliding summarization of long conversations
- Semantic memory (pgvector embeddings)
- Persistent state across sessions

### 4. Tool Integration

**Built-in tools:**
- Web search (Tavily API)
- Browser automation (Playwright)
- Code execution (E2B sandbox)
- File operations (sandboxed)
- API calling (any REST/GraphQL endpoint)
- Document analysis (PDF, DOCX, etc.)

**Extensible via MCP** (Model Context Protocol) for unlimited custom tools.

### 5. Real-Time Streaming

Watch your agent work:
- Status updates ("thinking", "searching", "executing")
- Tool calls with inputs/outputs
- Token-by-token text streaming
- Error tracking and recovery

### 6. Telegram Bot

Access your agent anywhere:
```
/ask research the latest AI news
/code write a python script to parse JSON
/analyze read this PDF and summarize it
/task add this to my todo list
```

## Environment Variables

```env
# OpenRouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BUDGET_MONTHLY=30.0

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Telegram Bot (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_URL=https://your-domain.com/telegram/webhook

# Database
DATABASE_URL=postgresql://user:password@localhost/agent_db

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

# Optional: Code execution sandbox
E2B_API_KEY=your_e2b_key
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  User Interface Layer                   │
│  ├── Web (Next.js)                      │
│  ├── Telegram Bot                       │
│  └── Mobile App (coming)                │
└─────────────┬───────────────────────────┘
              │
┌─────────────┴───────────────────────────┐
│  API Layer (FastAPI)                    │
│  ├── /agent/stream (SSE)                │
│  ├── /agent/run (HTTP)                  │
│  ├── /history                           │
│  └── /settings                          │
└─────────────┬───────────────────────────┘
              │
┌─────────────┴───────────────────────────┐
│  Agent Orchestration (PydanticAI)       │
│  ├── Task planning                      │
│  ├── Sub-agent spawning                 │
│  ├── State management                   │
│  └── Tool calling                       │
└─────────────┬───────────────────────────┘
              │
┌─────────────┴───────────────────────────┐
│  Model Router & LLM Access              │
│  ├── Cost tracking                      │
│  ├── Model selection                    │
│  ├── OpenRouter API                     │
│  └── Fallback chains                    │
└─────────────┬───────────────────────────┘
              │
┌─────────────┴───────────────────────────┐
│  Tools & External Services              │
│  ├── Tavily (web search)                │
│  ├── Playwright (browser)               │
│  ├── E2B (code execution)               │
│  └── File ops, APIs, etc.               │
└─────────────────────────────────────────┘
              │
┌─────────────┴───────────────────────────┐
│  Data Layer (Supabase)                  │
│  ├── PostgreSQL (tasks, memory)         │
│  ├── pgvector (embeddings)              │
│  └── File storage (documents)           │
└─────────────────────────────────────────┘
```

## Next Steps

1. **Read `SETUP.md`** - Detailed setup guide
2. **Read `DEPLOYMENT.md`** - VPS deployment guide
3. **Explore `/backend/app/tools/`** - See all available tools
4. **Try `/telegram-bot/README.md`** - Set up Telegram bot

## Monitoring & Debugging

- **Logs**: `docker logs agent-system-backend-1`
- **Database**: Connect via Supabase dashboard
- **Costs**: Dashboard at `/dashboard/costs`
- **API docs**: http://localhost:8000/docs (Swagger)

## Common Tasks

### Add a new tool

See `backend/app/tools/example_tool.py` - tools are just async functions with type hints.

### Change model routing logic

Edit `backend/app/agent/router.py` - extremely simple decision tree.

### Adjust cost limits

Edit `backend/app/config.py` - enforced at every API call.

### Deploy an update

```bash
git push
# VPS auto-pulls and restarts via webhook
```

## FAQ

**Q: Will this work offline?**
A: Partially. Web search, browser, and coding require internet. But local tasks (file ops, analysis of local docs) work offline.

**Q: Can I use local LLMs instead of OpenRouter?**
A: Yes! Set up Ollama on your VPS and add to fallback chain. See `backend/app/config.py`.

**Q: How do I add custom tools?**
A: Drop a new file in `backend/app/tools/`, define an async function with type hints, register in `backend/app/agent/tool_registry.py`. Done.

**Q: What if I hit my $30 budget?**
A: System stops making API calls and routes to local models or degrades gracefully. You get alerts at 80% and 95%.

**Q: Can I use this for production/business?**
A: This template is designed for personal use. For production, add auth, rate limits, audit logging, multi-user support.

## Support

- **Issues**: GitHub issues (or just reach out)
- **Docs**: Full API docs at `/docs` when running
- **Community**: Agent building community on Discord

---

**Ready to build? Start with `SETUP.md`.**
