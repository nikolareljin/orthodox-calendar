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
# Add TLS with:  sudo bash ~/orthodox-calendar/deploy/oracle/setup-tls.sh --email you@example.com
# deploy.sh (CI) calls /usr/local/bin/oc-certbot-provision (installed below).

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
  "${PYTHON}" "${PYTHON}-venv" \
  nginx nginx-common \
  git curl \
  certbot python3-certbot-nginx \
  cron \
  iptables iptables-persistent

echo "==> Opening ports 80 and 443 in OS firewall (Oracle Cloud blocks these by default)"
# Idempotent: delete all existing copies, then insert before the first REJECT/DROP
# so the ACCEPT is reachable even on chains with a terminal deny rule.
_open_port() {
  local ipt="$1" dport="$2"
  # Delete all existing copies of this rule — a stale appended rule may sit
  # after a terminal REJECT/DROP and be unreachable; -C cannot detect that.
  while "${ipt}" -D INPUT -m state --state NEW -p tcp --dport "${dport}" -j ACCEPT 2>/dev/null; do :; done
  # Re-insert before the first terminal catch-all REJECT/DROP (any source, any
  # dest) so targeted deny rules (fail2ban, source-specific) are unaffected.
  # Match both IPv4 (0.0.0.0/0) and IPv6 (::/0) catch-all addresses.
  local pos
  pos="$("${ipt}" -L INPUT --line-numbers -n 2>/dev/null | awk '
    /^[0-9]/ && ($2=="REJECT" || $2=="DROP") && $3=="all" &&
      ($5=="0.0.0.0/0" || $5=="::/0") &&
      ($6=="0.0.0.0/0" || $6=="::/0") &&
      ($2=="DROP" || $7=="reject-with") {
        if (!pos) pos=$1
      }
    END {if (pos) print pos}
  ')"
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

DEPLOY_DIR=""
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
if [[ "${SCRIPT_PATH}" == */* ]]; then
  CANDIDATE_DEPLOY_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" 2>/dev/null && pwd || true)"
  if [[ -f "${CANDIDATE_DEPLOY_DIR}/orthodox-calendar.service" \
      && -f "${CANDIDATE_DEPLOY_DIR}/nginx-backend.conf" \
      && -f "${CANDIDATE_DEPLOY_DIR}/oc-certbot-provision.sh" ]]; then
    DEPLOY_DIR="${CANDIDATE_DEPLOY_DIR}"
  fi
fi
if [[ -z "${DEPLOY_DIR}" ]]; then
  DEPLOY_DIR="${APP_DIR}/deploy/oracle"
fi
if [[ ! -f "${DEPLOY_DIR}/orthodox-calendar.service" \
    || ! -f "${DEPLOY_DIR}/nginx-backend.conf" \
    || ! -f "${DEPLOY_DIR}/oc-certbot-provision.sh" ]]; then
  echo "    deploy/oracle companion files missing — downloading fresh copies"
  DEPLOY_DIR="$(mktemp -d)"
  curl -fsSL "${REPO%.git}/raw/main/deploy/oracle/orthodox-calendar.service" \
    -o "${DEPLOY_DIR}/orthodox-calendar.service"
  curl -fsSL "${REPO%.git}/raw/main/deploy/oracle/nginx-backend.conf" \
    -o "${DEPLOY_DIR}/nginx-backend.conf"
  curl -fsSL "${REPO%.git}/raw/main/deploy/oracle/oc-certbot-provision.sh" \
    -o "${DEPLOY_DIR}/oc-certbot-provision.sh"
fi

echo "==> Creating Python virtualenv and installing backend dependencies"
sudo -u "${APP_USER}" "${PYTHON}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/backend/requirements.txt"

echo "==> Installing systemd service"
cp "${DEPLOY_DIR}/orthodox-calendar.service" /etc/systemd/system/
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

echo "==> Installing certbot provision wrapper"
# Always download from the canonical source — never install a file from the deploy
# user's writable checkout as a privileged command (tamper risk on re-runs).
curl -fsSL "${REPO%.git}/raw/main/deploy/oracle/oc-certbot-provision.sh" \
  -o /usr/local/bin/oc-certbot-provision
chown root:root /usr/local/bin/oc-certbot-provision
chmod 755 /usr/local/bin/oc-certbot-provision

cat > /usr/local/bin/oc-certbot-renew <<'WRAPPER'
#!/usr/bin/env bash
# Usage: oc-certbot-renew <nip-domain>
# Installed by setup.sh; run only via sudo from the deploy user.
set -euo pipefail
DOMAIN="$1"
_nip_re='^[0-9]+-[0-9]+-[0-9]+-[0-9]+\.nip\.io$'
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
DOMAIN_IP="${DOMAIN%.nip.io}"
DOMAIN_IP="${DOMAIN_IP//-/.}"
if ! [[ "${DOMAIN}" =~ ${_nip_re} ]] || ! [[ "${DOMAIN_IP}" =~ ${_valid_ipv4_re} ]]; then
  echo "ERROR: oc-certbot-renew: '${DOMAIN}' is not a valid nip.io hostname" >&2
  exit 1
fi
certbot renew --quiet --cert-name "${DOMAIN}"
WRAPPER
chown root:root /usr/local/bin/oc-certbot-renew
chmod 755 /usr/local/bin/oc-certbot-renew

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
# systemctl — only service restart and nginx lifecycle; no unit-file writes or
# daemon-reload (writing the unit and reloading systemd is root-only via setup.sh)
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${SERVICE}
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl start nginx
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now certbot.timer
# certbot — renewal only with fixed arguments, no wildcard injection surface
${APP_USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot renew --quiet
# Wrapper for TLS provisioning — hardcoded flags, no wildcard injection surface
${APP_USER} ALL=(ALL) NOPASSWD: /usr/local/bin/oc-certbot-provision
${APP_USER} ALL=(ALL) NOPASSWD: /usr/local/bin/oc-certbot-renew
SUDOERS
chown root:root /etc/sudoers.d/orthodox-calendar
chmod 440 /etc/sudoers.d/orthodox-calendar

echo "==> Installing nginx config"
cp "${DEPLOY_DIR}/nginx-backend.conf" /etc/nginx/sites-available/"${SERVICE}"
ln -sf /etc/nginx/sites-available/"${SERVICE}" /etc/nginx/sites-enabled/"${SERVICE}"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo ""
echo "==> Setup complete."
echo ""
public_ip="$(curl -fsS --max-time 10 https://ifconfig.me 2>/dev/null || true)"
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
if [[ -n "${public_ip}" ]] && ! [[ "${public_ip}" =~ ${_valid_ipv4_re} ]]; then
  echo "    WARNING: ifconfig.me returned '${public_ip}' (not a valid IPv4) — skipping nip.io hint"
  public_ip=""
fi
nip_domain=""
if [[ -n "${public_ip}" ]]; then
  nip_domain="${public_ip//./-}.nip.io"
  echo "    Backend API:  http://${public_ip}/api/v1/docs"
else
  echo "    Backend API:  http://<VM_PUBLIC_IP>/api/v1/docs"
fi
echo ""
echo "    Next steps:"
echo "    1. In Oracle Cloud console → Networking → VCN → Security Lists:"
echo "       Add Ingress rules for TCP 80 and TCP 443 (from 0.0.0.0/0)."
echo "    2. Set GitHub secrets BEFORE running the first deploy:"
echo "       OCI_HOST, OCI_USER, OCI_SSH_KEY, OCI_KNOWN_HOSTS"
if [[ -n "${nip_domain}" ]]; then
  echo "       VITE_API_BASE   = https://${nip_domain}"
  echo "       CERTBOT_EMAIL   = <your-email>"
else
  echo "       VITE_API_BASE   = https://<ip-with-hyphens>.nip.io"
  echo "       CERTBOT_EMAIL   = <your-email>"
fi
echo "       (see deploy/oracle/README.md for details)"
echo "    3. Run the first CI deploy — TLS is auto-provisioned via nip.io +"
echo "       Let's Encrypt using CERTBOT_EMAIL and the public IP above."
