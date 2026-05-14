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
# Use -C (check) before -A (append) so this is idempotent and safe on chains
# with any number of existing rules (avoids the failure mode of -I N when N > chain length).
_open_port() {
  local ipt="$1" dport="$2"
  # Skip if the rule already exists
  "${ipt}" -C INPUT -m state --state NEW -p tcp --dport "${dport}" -j ACCEPT 2>/dev/null && return 0
  # Insert before the first REJECT/DROP so the ACCEPT is reachable on Oracle
  # images that ship with a terminal deny rule in INPUT.
  local pos
  pos="$("${ipt}" -L INPUT --line-numbers -n 2>/dev/null | awk '/REJECT|DROP/{print $1; exit}')"
  if [[ -n "${pos}" ]]; then
    "${ipt}" -I INPUT "${pos}" -m state --state NEW -p tcp --dport "${dport}" -j ACCEPT
  else
    "${ipt}" -A INPUT -m state --state NEW -p tcp --dport "${dport}" -j ACCEPT
  fi
}
_open_port iptables  80
_open_port ip6tables 80
_open_port iptables  443
_open_port ip6tables 443
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
# apt — update cache and exact packages that deploy.sh may install as pre-flight
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get update -qq
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y curl
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y python3.12-venv
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y certbot
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y python3-certbot-nginx
# tee — write systemd unit and nginx site config files
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/systemd/system/${SERVICE}.service
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/nginx/sites-available/${SERVICE}
# systemctl — service management
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable ${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl start nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now certbot.timer
# nginx — config test
${APP_USER} ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
# nginx site symlink management
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/ln -sf /etc/nginx/sites-available/${SERVICE} /etc/nginx/sites-enabled/${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/rm -f /etc/nginx/sites-enabled/default
# certbot — exact invocations used by deploy.sh (* matches domain/email, no spaces)
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot --nginx -d * --non-interactive --agree-tos -m * --redirect
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot renew --quiet
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
