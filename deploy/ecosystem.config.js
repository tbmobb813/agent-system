// PM2 ecosystem config for agent-system
// Usage:
//   pm2 start deploy/ecosystem.config.js       (first run)
//   pm2 restart all                             (after deploy)
//   pm2 logs                                    (view logs)
//   pm2 save                                    (persist across reboots)

const path = require('path')
const ROOT = path.resolve(__dirname, '..')

module.exports = {
  apps: [
    // ── FastAPI backend ──────────────────────────────────────────────────────
    {
      name: 'agent-backend',
      cwd: path.join(ROOT, 'backend'),
      script: 'venv/bin/uvicorn',
      args: 'app.main:app --host 127.0.0.1 --port 8000 --workers 2',
      interpreter: 'none',
      env_file: path.join(ROOT, 'backend/.env'),
      env: {
        ENVIRONMENT: 'production',
      },
      // Restart policy
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      // Logging
      out_file: path.join(ROOT, 'logs/backend-out.log'),
      error_file: path.join(ROOT, 'logs/backend-err.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },

    // ── Next.js frontend ─────────────────────────────────────────────────────
    {
      name: 'agent-frontend',
      cwd: path.join(ROOT, 'frontend'),
      // standalone build output — faster startup than `next start`
      script: '.next/standalone/server.js',
      interpreter: 'node',
      env_file: path.join(ROOT, 'frontend/.env.local'),
      env: {
        PORT: '3003',
        HOSTNAME: '127.0.0.1',
        NODE_ENV: 'production',
      },
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      out_file: path.join(ROOT, 'logs/frontend-out.log'),
      error_file: path.join(ROOT, 'logs/frontend-err.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },
  ],
}
