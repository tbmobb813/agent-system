#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-time VPS setup for agent-system
# Run once as a non-root user with sudo access.
# Usage: bash deploy/setup.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$(whoami)"

echo "==> [1/7] System packages"
sudo apt-get update -q
sudo apt-get install -y -q \
    curl git build-essential \
    nginx certbot python3-certbot-nginx \
    python3.12 python3.12-venv python3-pip \
    postgresql postgresql-contrib

echo "==> [2/7] Node.js 20 + PM2"
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y -q nodejs
fi
sudo npm install -g pm2
pm2 startup systemd -u "$APP_USER" --hp "$HOME" | tail -1 | sudo bash

echo "==> [3/7] PostgreSQL — create DB + user"
DB_NAME="agent_db"
DB_USER="agent_user"
DB_PASS="$(openssl rand -hex 16)"

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || \
    echo "  (user already exists, skipping)"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || \
    echo "  (database already exists, skipping)"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

echo ""
echo "  !! SAVE THIS — add to backend .env:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME"
echo ""

echo "==> [4/7] Python virtualenv + dependencies"
cd "$REPO_DIR/backend"
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

echo "==> [5/7] Node dependencies + frontend build"
cd "$REPO_DIR/frontend"
npm ci --prefer-offline
npm run build

echo "==> [6/7] Nginx config"
sudo cp "$REPO_DIR/deploy/nginx.conf" /etc/nginx/sites-available/agent
sudo ln -sf /etc/nginx/sites-available/agent /etc/nginx/sites-enabled/agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> [7/7] PM2 — start services"
cd "$REPO_DIR"
pm2 start deploy/ecosystem.config.js
pm2 save

echo ""
echo "============================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Add DATABASE_URL (above) to backend/.env"
echo "  2. Add domain A record: agent.techtrendwire.com → $(curl -s ifconfig.me)"
echo "  3. Once DNS propagates, run:"
echo "       sudo certbot --nginx -d agent.techtrendwire.com"
echo "  4. Update CORS_ORIGINS + SITE_URL in backend/.env"
echo "  5. Update NEXT_PUBLIC_BACKEND_URL in frontend/.env.local"
echo "  6. Run: pm2 restart all"
echo "============================================================"
