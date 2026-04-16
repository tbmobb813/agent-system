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
# Use this value for BACKEND_API_KEY and NEXT_PUBLIC_BACKEND_API_KEY
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

### 8. Update env for HTTPS and restart
In `backend/.env`:
```
CORS_ORIGINS=["https://agent.techtrendwire.com"]
SITE_URL=https://agent.techtrendwire.com
```

In `frontend/.env.local`:
```
NEXT_PUBLIC_BACKEND_URL=https://agent.techtrendwire.com/api/backend
```

```bash
pm2 restart all
```

---

## Deploying Updates

After pushing changes to GitHub:
```bash
cd ~/agent-system
bash deploy/deploy.sh
```

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
