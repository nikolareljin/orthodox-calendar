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
PYTHON="python3.12"

echo "==> Installing system packages"
apt-get update -qq
# software-properties-common provides add-apt-repository (missing on minimal images)
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  software-properties-common ca-certificates gnupg2 lsb-release
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  "${PYTHON}" "${PYTHON}-venv" "${PYTHON}-distutils" \
  nginx nginx-common \
  git curl \
  certbot python3-certbot-nginx \
  iptables iptables-persistent

echo "==> Opening ports 80 and 443 in OS firewall (Oracle Cloud blocks these by default)"
iptables  -I INPUT  5 -m state --state NEW -p tcp --dport 80  -j ACCEPT
ip6tables -I INPUT  5 -m state --state NEW -p tcp --dport 80  -j ACCEPT
iptables  -I INPUT  5 -m state --state NEW -p tcp --dport 443 -j ACCEPT
ip6tables -I INPUT  5 -m state --state NEW -p tcp --dport 443 -j ACCEPT
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
unit_file="/etc/systemd/system/${SERVICE}.service"
escaped_app_dir="${APP_DIR//\//\\/}"
sed -i \
  -e "s/__APP_USER__/${APP_USER}/g" \
  -e "s/__APP_DIR__/${escaped_app_dir}/g" \
  "${unit_file}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl start "${SERVICE}"
echo "    Service status:"
systemctl is-active "${SERVICE}" && echo "    RUNNING" || echo "    FAILED — check: journalctl -u ${SERVICE}"

echo "==> Adding sudoers rules for the deploy user"
cat > /etc/sudoers.d/orthodox-calendar <<SUDOERS
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart ${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start nginx
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl enable nginx
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart nginx
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl enable certbot.timer
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get update -qq
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y python3.12-venv
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y curl
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y certbot
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y python3-certbot-nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/nginx/sites-available/${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/systemd/system/${SERVICE}.service
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/ln -sf /etc/nginx/sites-available/${SERVICE} /etc/nginx/sites-enabled/${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/rm -f /etc/nginx/sites-enabled/default
${APP_USER} ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot
SUDOERS
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
public_ip="$(curl -fsS ifconfig.me 2>/dev/null || true)"
if [[ -n "${public_ip}" ]]; then
  echo "    Backend API:  http://${public_ip}/api/v1/docs"
else
  echo "    Backend API:  http://<VM_PUBLIC_IP>/api/v1/docs"
fi
echo ""
echo "    Next steps:"
echo "    1. In Oracle Cloud console → Networking → VCN → Security Lists:"
echo "       Add Ingress rules for TCP 80 and TCP 443 (from 0.0.0.0/0)."
echo "    2. Run the first deploy (deploy.sh or manual-deploy.sh) — TLS is auto-"
echo "       provisioned via nip.io + Let's Encrypt using the public IP above."
echo "    3. Set GitHub secrets:"
echo "       VITE_API_BASE = https://<ip-with-hyphens>.nip.io"
echo "       (see deploy/oracle/README.md for all required secrets)"
