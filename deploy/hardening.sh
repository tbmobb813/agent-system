#!/usr/bin/env bash
# =============================================================================
# hardening.sh — Production hardening helper (UFW, logrotate, SSL via certbot)
# Usage:
#   bash deploy/hardening.sh --domain agent.example.com --email ops@example.com
#   bash deploy/hardening.sh --domain agent.example.com --no-certbot
# =============================================================================
set -euo pipefail

DOMAIN=""
EMAIL=""
NO_CERTBOT=0

usage() {
  echo "Usage: bash deploy/hardening.sh --domain <domain> [--email <email>] [--no-certbot]" >&2
}

is_option_token() {
  case "${1:-}" in
    --domain|--email|--no-certbot)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_valid_domain() {
  [[ "${1:-}" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$ ]]
}

is_valid_email() {
  [[ "${1:-}" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      if [[ -z "${2:-}" ]] || is_option_token "$2"; then
        echo "Error: --domain requires a value." >&2
        usage
        exit 1
      fi
      DOMAIN="$2"
      if ! is_valid_domain "$DOMAIN"; then
        echo "Error: --domain must be a valid domain value." >&2
        usage
        exit 1
      fi
      shift 2
      ;;
    --email)
      if [[ -z "${2:-}" ]] || is_option_token "$2"; then
        echo "Error: --email requires a value." >&2
        usage
        exit 1
      fi
      EMAIL="$2"
      if ! is_valid_email "$EMAIL"; then
        echo "Error: --email must be a valid email value." >&2
        usage
        exit 1
      fi
      shift 2
      ;;
    --no-certbot)
      NO_CERTBOT=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "--domain is required" >&2
  usage
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGROTATE_SRC="$REPO_DIR/deploy/logrotate-agent-system.conf"
LOGROTATE_DST="/etc/logrotate.d/agent-system"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

echo "==> [1/4] Installing hardening dependencies"
sudo apt-get update -q
sudo apt-get install -y -q ufw fail2ban logrotate certbot python3-certbot-nginx

need_cmd ufw
need_cmd logrotate


echo "==> [2/4] Applying firewall baseline (UFW)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw --force enable
sudo ufw status verbose


echo "==> [3/4] Installing log rotation policy"
if [[ ! -f "$LOGROTATE_SRC" ]]; then
  echo "Missing logrotate source file: $LOGROTATE_SRC" >&2
  exit 1
fi
sudo cp "$LOGROTATE_SRC" "$LOGROTATE_DST"
sudo chmod 644 "$LOGROTATE_DST"
sudo logrotate -d "$LOGROTATE_DST" >/dev/null

echo "==> [4/4] SSL certificate setup (certbot)"
if [[ "$NO_CERTBOT" -eq 1 ]]; then
  echo "Skipping certbot as requested (--no-certbot)."
else
  if [[ -n "$EMAIL" ]]; then
    sudo certbot --nginx --non-interactive --agree-tos --redirect -d "$DOMAIN" -m "$EMAIL"
  else
    sudo certbot --nginx --non-interactive --agree-tos --redirect -d "$DOMAIN" --register-unsafely-without-email
  fi
fi

echo "Hardening complete."
