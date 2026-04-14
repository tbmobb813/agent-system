# Setup Guide - Personal AI Agent System

This guide walks you through setting up your personal AI agent system from scratch. It should take about 1-2 hours total.

## Prerequisites

- VPS with Ubuntu 24 LTS (2 CPU, 8GB RAM, 100GB disk - you have this ✓)
- GitHub account (optional, for code storage)
- OpenRouter account (for LLM access)
- Supabase account (for database)

## Step 1: Prepare Your VPS

### 1.1 SSH into your VPS

```bash
ssh root@your-vps-ip
```

### 1.2 Update system

```bash
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3-pip git curl wget docker.io docker-compose-plugin
```

### 1.3 Add your user and configure SSH

```bash
adduser claude
usermod -aG sudo claude
usermod -aG docker claude

# Copy SSH key to new user
mkdir -p /home/claude/.ssh
cp ~/.ssh/authorized_keys /home/claude/.ssh/
chown -R claude:claude /home/claude/.ssh
```

### 1.4 Switch to your user

```bash
su - claude
```

## Step 2: Clone & Setup Backend

### 2.1 Clone the repository

```bash
cd ~
git clone https://github.com/yourusername/agent-system.git
cd agent-system/backend
```

Or if using the provided files:

```bash
mkdir -p ~/agent-system/backend
cd ~/agent-system/backend
# Copy all backend files here
```

### 2.2 Create Python virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 2.3 Download Playwright browsers (for browser automation)

```bash
playwright install chromium
# This downloads ~600MB, takes ~2-3 minutes
```

## Step 3: Setup Supabase Database

### 3.1 Create Supabase project

1. Go to https://supabase.com
2. Click "New Project"
3. Create project (name: `agent-system`, region closest to you)
4. Wait for setup (~2 minutes)

### 3.2 Run database migrations

Get your Supabase connection string from Project Settings → Database → Connection String.

```bash
# In supabase/migrations directory
# Run the SQL scripts in order:
psql "your-supabase-connection-string" < 001_initial_schema.sql
psql "your-supabase-connection-string" < 002_cost_tracking.sql
psql "your-supabase-connection-string" < 003_memory_tables.sql
```

**Or use Supabase SQL editor** (easier):
1. Go to Supabase Dashboard → SQL Editor
2. Create new query
3. Copy & paste content of each migration file
4. Run

### 3.3 Get your API keys

Go to Project Settings → API:
- Copy `URL` → `SUPABASE_URL`
- Copy `anon public` key → `SUPABASE_KEY`
- Copy `service_role secret` key → `SUPABASE_SERVICE_ROLE_KEY`

## Step 4: Setup OpenRouter

### 4.1 Create OpenRouter account

1. Go to https://openrouter.ai
2. Sign up (OAuth with GitHub easiest)
3. Go to Keys → Create new key
4. Copy the key → `OPENROUTER_API_KEY`

### 4.2 Add credits

1. Go to Account → Credit Balance
2. Add $30 credit (or however much you want to start with)

## Step 5: Create Environment File

### 5.1 Copy template

```bash
cd ~/agent-system/backend
cp .env.example .env
```

### 5.2 Edit .env

```bash
nano .env
```

Fill in these values (leave others as defaults for now):

```env
# Environment
ENVIRONMENT=production
DEBUG=false

# OpenRouter
OPENROUTER_API_KEY=sk_0abc123...
OPENROUTER_BUDGET_MONTHLY=30.0

# Database (Supabase)
DATABASE_URL=postgresql://user:password@db.supabase.co:5432/postgres
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGc...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...

# Tools (optional for now)
TAVILY_API_KEY=tvly-xxx  # Get from https://tavily.com
E2B_API_KEY=e2b_xxx     # Get from https://e2b.dev (for code execution)

# Security
ALLOWED_HOSTS=["your-domain.com", "your-vps-ip"]
CORS_ORIGINS=["https://your-domain.com", "http://localhost:3000"]
```

Save (Ctrl+X, Y, Enter).

## Step 6: Test Backend Locally

### 6.1 Start the server

```bash
cd ~/agent-system/backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 6.2 Test endpoints

In another terminal:

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs  # or visit in browser
```

You should see interactive API documentation with all endpoints.

### 6.3 Test a simple agent call

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-agent-test" \
  -d '{
    "query": "What is the capital of France?",
    "max_iterations": 3
  }'
```

Stop the server (Ctrl+C) when done testing.

## Step 7: Setup Frontend (Next.js)

### 7.1 Setup Node.js

```bash
# Install Node.js 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version  # Should be v20+
npm --version   # Should be v10+
```

### 7.2 Clone frontend

```bash
cd ~/agent-system
# Copy frontend files or clone
```

### 7.3 Install dependencies

```bash
cd frontend
npm install
```

### 7.4 Create .env.local

```bash
cat > .env.local << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
EOF
```

### 7.5 Test frontend locally

```bash
npm run dev
```

Visit http://localhost:3000 in browser. You should see the dashboard.

## Step 8: Setup Telegram Bot (Optional)

### 8.1 Create bot with BotFather

1. Open Telegram
2. Message @BotFather
3. Send `/newbot`
4. Follow prompts to create bot
5. Copy the token → `TELEGRAM_BOT_TOKEN`

### 8.2 Add to .env

```bash
TELEGRAM_BOT_TOKEN=123456:ABCdefg...
TELEGRAM_WEBHOOK_URL=https://your-domain.com/telegram/webhook
```

### 8.3 Test locally (for dev)

```bash
# The bot will use polling in dev mode
python telegram-bot/bot.py
```

## Step 9: Deploy to VPS with Docker

### 9.1 Create Docker Compose file

```bash
cd ~/agent-system
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=${DATABASE_URL}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=https://your-domain.com/api
      - NEXT_PUBLIC_SUPABASE_URL=${SUPABASE_URL}
      - NEXT_PUBLIC_SUPABASE_ANON_KEY=${SUPABASE_KEY}
    depends_on:
      - backend
    restart: always
EOF
```

### 9.2 Create Dockerfile for backend

```bash
cat > backend/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy app
COPY app/ ./app/
COPY .env .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
```

### 9.3 Create Dockerfile for frontend

```bash
cat > frontend/Dockerfile << 'EOF'
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public
COPY package.json .

EXPOSE 3000
CMD ["npm", "start"]
EOF
```

### 9.4 Build and start

```bash
cd ~/agent-system
docker-compose -f docker-compose.prod.yml up -d

# Verify running
docker ps
docker logs agent-system-backend-1
```

## Step 10: Setup Nginx Reverse Proxy

### 10.1 Install Nginx

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 10.2 Create Nginx config

```bash
sudo tee /etc/nginx/sites-available/agent-system > /dev/null << 'EOF'
upstream backend {
    server localhost:8000;
}

upstream frontend {
    server localhost:3000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /docs {
        proxy_pass http://backend/docs;
    }

    location /openapi.json {
        proxy_pass http://backend/openapi.json;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/agent-system /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t

# Reload
sudo systemctl restart nginx
```

### 10.3 Get SSL certificate

```bash
sudo certbot --nginx -d your-domain.com
```

Follow prompts. Should auto-configure HTTPS.

## Step 11: Create Systemd Service (Optional)

For auto-restart on reboot:

```bash
sudo tee /etc/systemd/system/agent-system.service > /dev/null << 'EOF'
[Unit]
Description=AI Agent System
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=claude
WorkingDirectory=/home/claude/agent-system
ExecStart=docker-compose -f docker-compose.prod.yml up
ExecStop=docker-compose -f docker-compose.prod.yml down
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable agent-system
sudo systemctl start agent-system
```

Check status:
```bash
sudo systemctl status agent-system
```

## Step 12: Verify Everything Works

### 12.1 Test web dashboard

```bash
open https://your-domain.com
```

Should see login screen or dashboard.

### 12.2 Test API

```bash
curl https://your-domain.com/api/health
# Should return: {"status": "ok", ...}
```

### 12.3 Test agent

```bash
curl -X POST https://your-domain.com/api/agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-agent-test" \
  -d '{"query": "What time is it?"}'
```

### 12.4 Check costs

```bash
curl https://your-domain.com/api/status/costs \
  -H "Authorization: Bearer sk-agent-test"
```

Should return current budget status.

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker logs agent-system-backend-1

# Common issues:
# - DATABASE_URL wrong: Check Supabase connection string
# - OPENROUTER_API_KEY invalid: Verify key in OpenRouter dashboard
# - Port 8000 in use: `sudo lsof -i :8000` and kill process
```

### Database connection failed

```bash
# Test Supabase connection
psql "your-connection-string" -c "SELECT 1"

# If fails: Check IP whitelist in Supabase
# Go to Project Settings → Database → Allowed IPs
# Add your VPS IP
```

### Telegram bot not responding

```bash
# Test bot
curl "https://api.telegram.org/botYOUR_TOKEN/getMe"

# If error: Check token is correct
# If works: Bot is running correctly
```

### High CPU usage

```bash
# Check what's running
docker stats

# If backend high:
# - Reduce max_iterations in agent config
# - Add caching layer
# - Use cheaper models for simple tasks
```

## Next Steps

1. **Add more tools**: See `backend/app/tools/` for examples
2. **Customize models**: Edit `backend/app/config.py` MODEL_PRICING
3. **Setup monitoring**: Install Prometheus/Grafana
4. **Add authentication**: Implement proper user auth
5. **Mobile app**: Build Flutter app or use Telegram bot

## Support

- **Logs**: `docker logs agent-system-backend-1`
- **Database**: Supabase dashboard
- **API Docs**: `https://your-domain.com/api/docs`

Good luck! 🚀
