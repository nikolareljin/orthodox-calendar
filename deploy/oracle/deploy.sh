#!/usr/bin/env bash
# Called by GitHub Actions over SSH to deploy a new backend version.
# Must be idempotent — safe to run multiple times.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/orthodox-calendar}"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:-}"
SERVICE="orthodox-calendar"

# ---------------------------------------------------------------------------
# Pre-flight: ensure runtime tools are present (minimal Oracle Ubuntu may
# lack these even after initial setup.sh if packages were purged/upgraded).
# setup.sh must have granted the deploy user the matching sudoers entries.
# ---------------------------------------------------------------------------
_apt_updated=false
_apt_install() {
  if [[ "${_apt_updated}" == "false" ]]; then
    echo "    Updating apt cache"
    sudo apt-get update -qq
    _apt_updated=true
  fi
  echo "    Installing missing package: $1"
  sudo apt-get install -y "$1"
}

echo "==> Pre-flight checks"
if ! command -v curl > /dev/null 2>&1; then
  _apt_install curl
fi
if ! command -v python3.12 > /dev/null 2>&1; then
  echo "ERROR: python3.12 is required but not found — run deploy/oracle/setup.sh on the server first" >&2
  exit 1
fi
if ! dpkg -s python3.12-venv > /dev/null 2>&1; then
  _apt_install python3.12-venv
fi
if ! command -v nginx > /dev/null 2>&1; then
  _apt_install nginx
fi
if ! command -v certbot > /dev/null 2>&1; then
  _apt_install certbot
fi
if ! dpkg -s python3-certbot-nginx > /dev/null 2>&1; then
  _apt_install python3-certbot-nginx
fi

APP_USER="$(id -un)"

echo "==> Detecting public IP"
_raw="$(curl -sf --max-time 5 -H 'Authorization: Bearer Oracle' 'http://169.254.169.254/opc/v2/vnics/' 2>/dev/null || true)"
PUBLIC_IP="$(echo "${_raw}" | python3.12 -c 'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' 2>/dev/null || true)"
if [[ -z "${PUBLIC_IP}" ]]; then
  _raw="$(curl -sf --max-time 5 'http://169.254.169.254/opc/v1/vnics/' 2>/dev/null || true)"
  PUBLIC_IP="$(echo "${_raw}" | python3.12 -c 'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' 2>/dev/null || true)"
fi
if [[ -z "${PUBLIC_IP}" ]]; then
  PUBLIC_IP="$(curl -sf --max-time 10 ifconfig.me 2>/dev/null || true)"
fi
unset _raw
# Validate before use — reject anything that is not a plain IPv4 address to
# prevent nginx config injection from a malformed or intercepted HTTP response.
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
  echo "    WARNING: detected value '${PUBLIC_IP}' is not a valid IPv4 address — ignoring"
  PUBLIC_IP=""
fi
NIP_DOMAIN=""
SERVER_NAME="_"
if [[ -n "${PUBLIC_IP}" ]]; then
  NIP_DOMAIN="${PUBLIC_IP//./-}.nip.io"
  SERVER_NAME="${NIP_DOMAIN}"
  echo "    Public IP: ${PUBLIC_IP} → ${NIP_DOMAIN}"
else
  echo "    Could not detect public IP — nginx will use catch-all server_name"
fi

# Systemd unit and nginx site config are created by setup.sh (root-only).
# Writing the unit file from a deploy user + daemon-reload + restart is a
# privilege-escalation path; require setup.sh to have been run instead.
UNIT_FILE="/etc/systemd/system/${SERVICE}.service"
if [[ ! -f "${UNIT_FILE}" ]]; then
  echo "ERROR: systemd unit ${UNIT_FILE} not found." >&2
  echo "       Run deploy/oracle/setup.sh on the server first." >&2
  exit 1
fi

NGINX_SITE="/etc/nginx/sites-available/${SERVICE}"
if [[ ! -f "${NGINX_SITE}" ]]; then
  echo "ERROR: nginx site config ${NGINX_SITE} not found." >&2
  echo "       Run deploy/oracle/setup.sh on the server first." >&2
  exit 1
fi

if ! systemctl is-active --quiet nginx 2>/dev/null; then
  sudo systemctl enable nginx
  sudo systemctl start nginx
fi

if [[ -n "${NIP_DOMAIN}" ]]; then
  # Cert file existing is not enough — nginx may have been reset (e.g. by
  # re-running setup.sh) and lost the SSL server block. Check both.
  if [[ -f "/etc/letsencrypt/live/${NIP_DOMAIN}/fullchain.pem" ]] \
      && grep -q "ssl_certificate" "${NGINX_SITE}" 2>/dev/null; then
    echo "==> TLS already active for ${NIP_DOMAIN}"
  else
    echo "==> Obtaining TLS certificate for ${NIP_DOMAIN}"
    sudo certbot --nginx -d "${NIP_DOMAIN}" \
      --non-interactive --agree-tos \
      -m "nikola.reljin@gmail.com" \
      --redirect
    echo "    Certificate obtained. Backend available at https://${NIP_DOMAIN}"
  fi
fi

# Enable automatic cert renewal — certbot renew is a no-op until 30 days before
# expiry, so a daily check is fine. Prefer the systemd timer that certbot installs
# via apt; fall back to a single crontab line if the timer is absent.
if systemctl list-unit-files --no-legend certbot.timer 2>/dev/null | grep -q '^certbot\.timer'; then
  sudo systemctl enable --now certbot.timer
  echo "==> certbot.timer enabled for automatic renewal"
else
  # certbot renew needs root; use sudo (deploy user has NOPASSWD for certbot in sudoers)
  CRON_JOB="0 3 * * * sudo certbot renew --quiet"
  if ! crontab -l 2>/dev/null | grep -qF "certbot renew"; then
    ( crontab -l 2>/dev/null; echo "${CRON_JOB}" ) | crontab -
    echo "==> Daily certbot renewal cron installed (03:00)"
  fi
fi

echo "==> Installing scoped backend release"
mkdir -p "${APP_DIR}/backend"
if [[ -n "${RELEASE_ARCHIVE}" ]]; then
  if [[ ! -f "${RELEASE_ARCHIVE}" ]]; then
    echo "ERROR: release archive not found: ${RELEASE_ARCHIVE}" >&2
    exit 1
  fi
  tmpdir="$(mktemp -d)"
  cleanup() {
    rm -rf "${tmpdir}"
    rm -f "${RELEASE_ARCHIVE}"
  }
  trap cleanup EXIT
  tar -xzf "${RELEASE_ARCHIVE}" -C "${tmpdir}"
  find "${tmpdir}" \( -type d -name "__pycache__" -o -type f -name "*.py[co]" \) -exec rm -rf {} +
  test -d "${tmpdir}/backend/app"
  test -f "${tmpdir}/backend/requirements.txt"
  find "${APP_DIR}" -mindepth 1 -maxdepth 1 \
    ! -name ".venv" \
    ! -name "backend" \
    -exec rm -rf {} +
  find "${APP_DIR}/backend" -mindepth 1 -maxdepth 1 \
    ! -name "app" \
    ! -name "requirements.txt" \
    -exec rm -rf {} +
  rm -rf "${APP_DIR}/backend/app"
  cp -a "${tmpdir}/backend/app" "${APP_DIR}/backend/app"
  cp "${tmpdir}/backend/requirements.txt" "${APP_DIR}/backend/requirements.txt"
else
  test -d "${APP_DIR}/backend/app"
  test -f "${APP_DIR}/backend/requirements.txt"
fi

cd "${APP_DIR}"

echo "==> Ensuring Python virtualenv"
_venv_ok=false
if [[ -f ".venv/bin/pip" ]] && .venv/bin/python -c 'import sys' > /dev/null 2>&1; then
  _py_ver=$(.venv/bin/python -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))' 2>/dev/null || echo "")
  if [[ "${_py_ver}" == "3.12" ]]; then
    _venv_ok=true
  else
    echo "    Existing venv uses Python ${_py_ver:-unknown} (expected 3.12) — rebuilding"
  fi
fi
if [[ "${_venv_ok}" == "false" ]]; then
  rm -rf .venv
  if ! python3.12 -m venv .venv 2>/dev/null; then
    _apt_install python3.12-venv
    python3.12 -m venv .venv
  fi
  echo "    Created virtualenv with python3.12"
  # Note: a broken interpreter symlink is already caught by the import-sys
  # check above (triggers a rebuild). Only an in-place patch upgrade that
  # keeps the same binary path but changes compiled-wheel ABI is missed;
  # remove .venv manually before deploying if that situation arises.
fi

echo "==> Installing/updating Python dependencies"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r backend/requirements.txt

echo "==> Restarting service"
sudo systemctl restart "${SERVICE}"

echo "==> Waiting for service to become healthy"
for i in $(seq 1 10); do
  sleep 2
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "    Health check passed (attempt ${i})"
    exit 0
  fi
  echo "    Attempt ${i}/10 — not yet healthy"
done

echo "ERROR: service did not become healthy after 20 s" >&2
journalctl -u "${SERVICE}" --no-pager -n 30 >&2
exit 1
