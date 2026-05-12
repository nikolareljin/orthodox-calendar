#!/usr/bin/env bash
# One-time setup script for Oracle Cloud Always Free VM (Ubuntu 22.04).
# Run as root (or with sudo) immediately after first login.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nikolareljin/orthodox-calendar/main/deploy/oracle/setup.sh | sudo bash
#   — or —
#   sudo bash deploy/oracle/setup.sh
#
# After this script, the backend is live on port 80.
# Add a domain + TLS with:  sudo certbot --nginx -d your.domain.com

set -euo pipefail

APP_USER="${APP_USER:-ubuntu}"
APP_DIR="/home/${APP_USER}/orthodox-calendar"
REPO="https://github.com/nikolareljin/orthodox-calendar.git"
SERVICE="orthodox-calendar"
PYTHON="python3.11"

echo "==> Installing system packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  "${PYTHON}" "${PYTHON}-venv" \
  nginx git curl \
  certbot python3-certbot-nginx \
  iptables iptables-persistent

echo "==> Opening ports 80 and 443 in OS firewall (Oracle Cloud blocks these by default)"
iptables  -I INPUT  6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
iptables  -I INPUT  7 -m state --state NEW -p tcp --dport 443 -j ACCEPT
ip6tables -I INPUT  6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
ip6tables -I INPUT  7 -m state --state NEW -p tcp --dport 443 -j ACCEPT
# Persist so rules survive reboot
netfilter-persistent save

echo "==> Cloning repository into ${APP_DIR}"
if [[ -d "${APP_DIR}" ]]; then
  echo "    Directory exists — skipping clone; run 'git pull' manually if needed."
else
  sudo -u "${APP_USER}" git clone "${REPO}" "${APP_DIR}"
fi

echo "==> Creating Python virtualenv and installing backend dependencies"
sudo -u "${APP_USER}" "${PYTHON}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/backend/requirements.txt"

echo "==> Installing systemd service"
cp "$(dirname "$0")/orthodox-calendar.service" /etc/systemd/system/
# Patch the user in the unit file if APP_USER is not ubuntu
sed -i "s/User=ubuntu/User=${APP_USER}/" /etc/systemd/system/"${SERVICE}.service"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl start "${SERVICE}"
echo "    Service status:"
systemctl is-active "${SERVICE}" && echo "    RUNNING" || echo "    FAILED — check: journalctl -u ${SERVICE}"

echo "==> Adding sudoers rule so the deploy user can restart the service without a password"
echo "${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart ${SERVICE}" \
  > /etc/sudoers.d/orthodox-calendar
chmod 440 /etc/sudoers.d/orthodox-calendar

echo "==> Installing nginx config"
cp "$(dirname "$0")/nginx-backend.conf" /etc/nginx/sites-available/"${SERVICE}"
ln -sf /etc/nginx/sites-available/"${SERVICE}" /etc/nginx/sites-enabled/"${SERVICE}"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo ""
echo "==> Setup complete."
echo ""
echo "    Backend API:  http://$(curl -s ifconfig.me)/docs"
echo ""
echo "    Next steps:"
echo "    1. In Oracle Cloud console → Networking → VCN → Security Lists:"
echo "       Add Ingress rules for TCP 80 and TCP 443 (from 0.0.0.0/0)."
echo "    2. Point a domain at this IP, then run:"
echo "       sudo certbot --nginx -d your.domain.com"
echo "    3. Set GitHub secrets (see deploy/oracle/README.md)."
