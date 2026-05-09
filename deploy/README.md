# Deployment Guide — agent.techtrendwire.com

## Stack
- **Frontend**: Next.js (standalone, port 3003)
- **Backend**: FastAPI + uvicorn (port 8000)
- **Proxy**: Nginx (public, handles SSL + routing)
- **Process manager**: PM2 (auto-restart + reboot persistence)
- **Database**: PostgreSQL

---

## First-Time Setup

### 1. Clone the repo on your VPS
```bash
git clone https://github.com/YOUR_USERNAME/agent-system.git ~/agent-system
cd ~/agent-system
```

### 2. Create environment files
```bash
# Backend
cp deploy/.env.backend.example backend/.env
nano backend/.env   # fill in your keys

# Frontend
cp deploy/.env.frontend.example frontend/.env.local
nano frontend/.env.local   # fill in keys (must match backend)
```

### 3. Generate a strong API key
```bash
echo "sk-agent-$(openssl rand -hex 24)"
# Use this value for BACKEND_API_KEY
```

### 4. Run setup
```bash
bash deploy/setup.sh
```

This will:
- Install PostgreSQL, Nginx, Node.js 20, PM2, Python deps
- Create the database and print the DATABASE_URL
- Build the frontend
- Start both services with PM2
- Configure Nginx

### 5. Add DATABASE_URL to backend/.env
The setup script prints the generated DB URL — add it to `backend/.env`.

### 6. Point your domain
In Hostinger DNS, add an **A record**:
- Name: `agent`
- Value: your VPS IP
- TTL: 300

### 7. Enable SSL
Once DNS propagates (check with `dig agent.techtrendwire.com`):
```bash
sudo certbot --nginx -d agent.techtrendwire.com
```

### 7b. Apply security hardening baseline
```bash
bash deploy/hardening.sh --domain agent.techtrendwire.com --email you@example.com
```

This applies:
- UFW firewall baseline (allow `OpenSSH`, `80`, `443`; deny other inbound — if your SSH daemon uses a custom port, allow that port/profile before or when applying hardening)
- Installs `fail2ban` package baseline (default service/jail configuration from distro package)
- `logrotate` policy for `logs/*.log`
- certbot HTTPS setup (unless `--no-certbot` is passed)

### 8. Update env for HTTPS and restart
In `backend/.env`:
```
CORS_ORIGINS=["https://agent.techtrendwire.com"]
SITE_URL=https://agent.techtrendwire.com
```

In `frontend/.env.local`:
```
BACKEND_URL=http://127.0.0.1:8000
```

```bash
pm2 restart all
```

---

## Deploying Updates

Create an optional deploy env file once:
```bash
cp deploy/.env.deploy.example deploy/.env.deploy
nano deploy/.env.deploy
```

After pushing changes to GitHub:
```bash
cd ~/agent-system
bash deploy/deploy.sh
```

`deploy/deploy.sh` auto-loads `deploy/.env.deploy` when present.

### Optional: persist deploy monitoring env vars
Add this block to your shell profile (`~/.bashrc`) if you want these defaults every session:

```bash
# agent-system deploy defaults
export MONITOR_BASE_URL="https://agent.techtrendwire.com"
# Leave empty to disable webhook alerts from deploy/monitoring-smoke.sh
export ALERT_WEBHOOK_URL=""
```

Use shell-profile exports only if you prefer host-wide defaults over a repo-local `deploy/.env.deploy`.

---

## Useful Commands

```bash
pm2 status              # check both services
pm2 logs                # tail all logs
pm2 logs agent-backend  # backend only
pm2 logs agent-frontend # frontend only
pm2 restart all         # restart both
sudo nginx -t           # test nginx config
sudo systemctl reload nginx
bash deploy/monitoring-smoke.sh --base-url https://agent.techtrendwire.com
```

## Monitoring Baseline

### Smoke checks with optional alert hook
```bash
# One-shot health checks
bash deploy/monitoring-smoke.sh --base-url https://agent.techtrendwire.com

# Send failure alerts to your webhook (Slack-style JSON payload)
ALERT_WEBHOOK_URL=https://hooks.example.com/xxx \
      bash deploy/monitoring-smoke.sh --base-url https://agent.techtrendwire.com
```

### Recommended cron (every 5 minutes)
```bash
crontab -e
*/5 * * * * ALERT_WEBHOOK_URL=https://hooks.example.com/xxx /bin/bash ~/agent-system/deploy/monitoring-smoke.sh --base-url https://agent.techtrendwire.com >> ~/agent-system/logs/monitoring-cron.log 2>&1
```

---

## Architecture

```
Internet (HTTPS)
      │
      ▼
Nginx :443 (agent.techtrendwire.com)
      │
      ├── /api/backend/agent/stream  →  FastAPI :8000  (proxy_buffering off — SSE)
      ├── /api/backend/*             →  FastAPI :8000
      └── /*                        →  Next.js :3003
```
