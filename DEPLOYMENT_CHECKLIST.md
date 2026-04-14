# 🚀 Deployment Checklist & Production Readiness

This guide ensures your agent system is production-ready before deployment to your VPS.

## Pre-Deployment Checklist

### Code Quality
- [ ] All files copied to `/home/claude/agent-system/`
- [ ] `.env.example` reviewed and filled in with real values
- [ ] `.gitignore` includes `.env` (never commit secrets)
- [ ] `requirements.txt` has all dependencies
- [ ] `docker-compose.yml` is correctly configured

### Security
- [ ] OPENROUTER_API_KEY is strong and kept secret
- [ ] Supabase service role key not exposed in client code
- [ ] CORS_ORIGINS contains only your domain
- [ ] ALLOWED_HOSTS configured for your VPS
- [ ] Database credentials stored as environment variables
- [ ] API key authentication enabled on all endpoints

### Database
- [ ] Supabase project created and tables initialized
- [ ] All migrations run successfully
- [ ] Backups configured in Supabase
- [ ] Row-level security (RLS) policies enabled
- [ ] Connection string tested

### API & LLM
- [ ] OpenRouter account created and funded
- [ ] OpenRouter API key generated and verified
- [ ] Models in config are available on OpenRouter
- [ ] Cost limits set to $30/month
- [ ] Fallback chain configured

### Monitoring
- [ ] Logging configured (check Docker logs work)
- [ ] Error tracking set up (optional: Sentry)
- [ ] Cost tracking database tables ready
- [ ] Budget alerts configured

## Local Testing (Before Deployment)

### Test Locally First

```bash
# 1. Start local environment
cd ~/agent-system
docker-compose up

# 2. Wait for services to start
sleep 30

# 3. Test backend health
curl http://localhost:8000/health

# 4. Test frontend
open http://localhost:3000

# 5. Run a test agent query
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is 2+2?"}'

# 6. Check costs
curl http://localhost:8000/status/costs

# 7. View logs
docker-compose logs backend
docker-compose logs frontend
```

### Verify All Components

```bash
# Check all containers running
docker-compose ps
# Should show: postgres, backend, frontend, redis all UP

# Test database
docker-compose exec postgres psql -U postgres -d agent_db -c "SELECT 1;"

# Test Redis
docker-compose exec redis redis-cli ping
# Should return: PONG

# Test API documentation
open http://localhost:8000/docs
```

## VPS Deployment Steps

### Step 1: Prepare VPS

```bash
# SSH to VPS
ssh root@your-vps-ip

# Create non-root user
adduser claude
usermod -aG sudo claude
usermod -aG docker claude

# Install Docker if needed
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx

# Switch to user
su - claude
```

### Step 2: Copy Code to VPS

```bash
# From your local machine
scp -r ~/agent-system claude@your-vps-ip:~/

# Or clone from GitHub
ssh claude@your-vps-ip
cd ~ && git clone https://github.com/yourusername/agent-system.git
```

### Step 3: Setup Environment

```bash
cd ~/agent-system
cp .env.example .env
nano .env  # Fill in all values

# Verify sensitive values
cat .env | grep -E "OPENROUTER|SUPABASE|TOKEN" 
# Should show values, not defaults
```

### Step 4: Test on VPS

```bash
# Start services
docker-compose up -d

# Wait for startup
sleep 30

# Check status
docker-compose ps
docker-compose logs

# Test local connection
curl http://localhost:8000/health
```

### Step 5: Setup Nginx Reverse Proxy

```bash
# Create Nginx config
sudo tee /etc/nginx/sites-available/agent-system > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
    
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/agent-system /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### Step 6: Get SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com

# Follow prompts to accept terms
# Certbot auto-redirects HTTP to HTTPS
```

### Step 7: Setup Auto-Restart

```bash
# Create systemd service
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
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable agent-system
sudo systemctl start agent-system
```

### Step 8: Configure Firewall

```bash
# UFW firewall rules
sudo ufw enable
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

## Post-Deployment Verification

### Verify Everything Works

```bash
# Test from external (not on VPS)
curl https://your-domain.com/health
# Should return JSON health status

# Test API
curl -X POST https://your-domain.com/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# Check certificate
curl -I https://your-domain.com
# Should show valid certificate
```

### Monitor Logs

```bash
# Real-time logs
docker-compose logs -f

# Backend logs only
docker-compose logs -f backend

# Check for errors
docker-compose logs backend | grep ERROR

# Database activity
docker-compose logs postgres | head -20
```

### Check Resource Usage

```bash
# CPU and memory
docker stats

# Disk space
df -h

# Network connections
sudo netstat -tulpn | grep LISTEN
```

## Troubleshooting Deployment

### Service Won't Start

```bash
# Check logs
systemctl status agent-system
journalctl -u agent-system -n 50

# Docker logs
docker-compose logs
docker-compose logs backend  # Specific service
```

### Database Connection Failed

```bash
# Check Supabase connection string
echo $DATABASE_URL

# Test connection
docker exec agent-system-backend-1 psql -c "SELECT 1;"

# Verify IP whitelist in Supabase dashboard
# Settings → Database → Allowed IPs
```

### High CPU Usage

```bash
# See which container uses CPU
docker stats

# If backend high:
# - Reduce max_iterations in config
# - Check for infinite loops in agent
# - Add caching layer

# Restart problematic service
docker-compose restart backend
```

### Out of Disk Space

```bash
# Check disk usage
du -sh ~/agent-system/*

# Clean up Docker
docker system prune -a

# Check logs size
docker logs --tail 100 agent-system-backend-1
# Consider log rotation
```

## Scaling Considerations

### For Heavy Usage

1. **Horizontal Scaling**
   - Run multiple backend instances behind load balancer
   - Use Docker Compose replica feature
   - Add HAProxy or nginx load balancer

2. **Caching**
   - Redis already configured
   - Enable query caching
   - Implement response memoization

3. **Database**
   - Upgrade Supabase tier
   - Add read replicas
   - Optimize queries with better indexes

4. **Background Jobs**
   - Move expensive operations to async queue
   - Use Celery + Redis for job processing
   - Implement scheduled tasks (cost reporting, etc.)

## Backup & Recovery

### Database Backups

```bash
# Manual backup (via Supabase dashboard)
1. Go to Supabase dashboard
2. Backups section
3. Download backup

# Automated backups (Supabase does this automatically)
# Check: Settings → Backups
```

### File Backups

```bash
# Backup .env and config
tar -czf agent-system-config-backup.tar.gz .env docker-compose.yml

# Keep offsite
scp agent-system-config-backup.tar.gz yourserver.com:~/backups/
```

### Recovery Procedure

```bash
# If something fails
1. Check logs: docker-compose logs
2. Restart service: docker-compose restart backend
3. If database issue: restore from Supabase backup
4. Re-deploy code: git pull && docker-compose up -d
```

## Maintenance Tasks

### Weekly
- [ ] Check disk space: `df -h`
- [ ] Review error logs: `docker-compose logs backend | grep ERROR`
- [ ] Monitor costs: Dashboard at `/dashboard/costs`

### Monthly
- [ ] Update dependencies: `docker-compose pull && docker-compose build`
- [ ] Backup database: Via Supabase console
- [ ] Review and optimize queries

### Quarterly
- [ ] Security audit: Check for exposed keys
- [ ] Performance review: Check response times
- [ ] Cost analysis: Review spending trends

## Performance Tuning

### Backend Optimization

```python
# In config.py:
MAX_WORKERS = 4  # Increase for more concurrent requests
CACHE_TTL = 3600  # Increase to reduce API calls
BATCH_SIZE = 10  # Batch operations for efficiency
```

### Database Optimization

```sql
-- Add missing indexes
CREATE INDEX idx_tasks_user_created ON tasks(user_id, created_at DESC);

-- Archive old data
DELETE FROM tasks WHERE created_at < NOW() - INTERVAL '90 days';
```

### Frontend Optimization

```bash
# Build optimized production build
npm run build
npm prune --production
```

## Security Hardening

### Before Going Live

- [ ] Change default passwords
- [ ] Enable 2FA on Supabase/OpenRouter
- [ ] Setup firewall rules (UFW configured)
- [ ] Configure SSH key-only authentication
- [ ] Enable HTTPS only (Certbot configured)
- [ ] Setup rate limiting (can add in Nginx)
- [ ] Enable CORS restrictions
- [ ] Audit environment variables

### Ongoing Security

- [ ] Monitor for suspicious activity
- [ ] Keep system packages updated
- [ ] Rotate API keys periodically
- [ ] Review access logs
- [ ] Update dependencies regularly

## Success Metrics

Your deployment is successful when:

✅ https://your-domain.com loads (dashboard)
✅ https://your-domain.com/api/health returns 200
✅ Agent queries execute and return results
✅ Cost tracking shows accurate spending
✅ Logs show no ERROR messages
✅ Database backups are configured
✅ HTTPS certificate is valid
✅ Docker containers auto-restart
✅ Performance metrics are good (<2s response time)

---

**You're now ready for production!**

If issues arise, check the logs first:
```bash
docker-compose logs -f
```

Good luck! 🚀
