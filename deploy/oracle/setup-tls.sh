#!/usr/bin/env bash
# setup-tls.sh — obtain a Let's Encrypt TLS certificate via nip.io and enable
# automatic renewal. Safe to run multiple times (idempotent).
#
# Usage:
#   sudo bash setup-tls.sh --email you@example.com
#   sudo bash setup-tls.sh --email you@example.com --ip 1.2.3.4
#
# --email is required. sudo resets the environment, so env-var workarounds
# are unreliable; pass the address via --email instead.
#
# nip.io maps <dashed-ip>.nip.io → the same IP automatically, so no domain
# registration is needed. Certificates are valid for 90 days; this script also
# installs automatic renewal via certbot.timer if present (schedule is
# distro-defined), or a daily 03:00 cron as fallback. No-op until 30 days
# before expiry.
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
FORCED_IP=""
APP_USER="${APP_USER:-ubuntu}"
APP_DIR="/home/${APP_USER}/orthodox-calendar"
REPO="https://github.com/nikolareljin/orthodox-calendar.git"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip)
      if [[ $# -lt 2 ]]; then echo "ERROR: --ip requires an argument" >&2; exit 1; fi
      FORCED_IP="$2"; shift 2 ;;
    --email)
      if [[ $# -lt 2 ]]; then echo "ERROR: --email requires an argument" >&2; exit 1; fi
      CERTBOT_EMAIL="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${CERTBOT_EMAIL}" ]]; then
  echo "ERROR: --email <address> is required for Let's Encrypt registration." >&2
  echo "       Usage: sudo bash setup-tls.sh --email you@example.com" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_apt_updated=false
_apt_install() {
  if [[ "${_apt_updated}" == "false" ]]; then
    echo "    Updating apt cache"
    apt-get update -qq
    _apt_updated=true
  fi
  echo "    Installing: $1"
  DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"
}
_pkg_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -qx 'install ok installed'
}

# ---------------------------------------------------------------------------
# 0 — Ensure curl is present (needed for IP detection below)
# ---------------------------------------------------------------------------
if ! command -v curl > /dev/null 2>&1; then
  echo "==> Installing curl"
  _apt_install curl
fi

# ---------------------------------------------------------------------------
# 1 — Resolve public IP → nip.io domain
# ---------------------------------------------------------------------------
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
if [[ -n "${FORCED_IP}" ]]; then
  PUBLIC_IP="${FORCED_IP}"
else
  echo "==> Detecting public IP"
  _raw="$(curl -sf --max-time 5 -H 'Authorization: Bearer Oracle' \
    'http://169.254.169.254/opc/v2/vnics/' 2>/dev/null || true)"
  PUBLIC_IP="$(echo "${_raw}" | python3 -c \
    'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' \
    2>/dev/null || true)"
  if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
    PUBLIC_IP=""
  fi
  if [[ -z "${PUBLIC_IP}" ]]; then
    _raw="$(curl -sf --max-time 5 'http://169.254.169.254/opc/v1/vnics/' 2>/dev/null || true)"
    PUBLIC_IP="$(echo "${_raw}" | python3 -c \
      'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' \
      2>/dev/null || true)"
    if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
      PUBLIC_IP=""
    fi
  fi
  if [[ -z "${PUBLIC_IP}" ]]; then
    PUBLIC_IP="$(curl -sf --max-time 10 https://ifconfig.me 2>/dev/null || true)"
  fi
  unset _raw
fi

if [[ -z "${PUBLIC_IP}" ]]; then
  echo "ERROR: could not determine public IP. Pass it with --ip <address>." >&2
  exit 1
fi
# Reject non-IPv4 values to prevent nginx config injection from a malformed
# IMDS/ifconfig.me response or an invalid --ip argument.
if ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
  echo "ERROR: '${PUBLIC_IP}' is not a valid IPv4 address." >&2
  exit 1
fi

NIP_DOMAIN="${PUBLIC_IP//./-}.nip.io"
echo "==> IP: ${PUBLIC_IP}  →  domain: ${NIP_DOMAIN}"

NGINX_SITE="/etc/nginx/sites-available/orthodox-calendar"
if [[ ! -f "${NGINX_SITE}" ]]; then
  echo "ERROR: nginx site ${NGINX_SITE} not found — run setup.sh first." >&2
  exit 1
fi
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/orthodox-calendar"
if [[ ! -L "${NGINX_SITE_ENABLED}" ]]; then
  echo "ERROR: nginx sites-enabled symlink ${NGINX_SITE_ENABLED} not found — run setup.sh first." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 2 — Install certbot if absent
# ---------------------------------------------------------------------------
if ! command -v certbot > /dev/null 2>&1; then
  echo "==> Installing certbot"
  _apt_install certbot
fi
if ! _pkg_installed python3-certbot-nginx; then
  _apt_install python3-certbot-nginx
fi

# ---------------------------------------------------------------------------
# 3 — Provision or renew the certificate using the shared root-owned wrapper.
# setup.sh installs the same helper for deploy.sh, so nginx/TLS recovery logic
# stays in one place.
# ---------------------------------------------------------------------------
PROVISION_HELPER=""
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
if [[ "${SCRIPT_PATH}" == */* ]]; then
  CANDIDATE_DEPLOY_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" 2>/dev/null && pwd || true)"
  CANDIDATE_HELPER="${CANDIDATE_DEPLOY_DIR}/oc-certbot-provision.sh"
  if [[ -f "${CANDIDATE_HELPER}" ]]; then
    PROVISION_HELPER="${CANDIDATE_HELPER}"
  fi
fi
if [[ -z "${PROVISION_HELPER}" && -f "${APP_DIR}/deploy/oracle/oc-certbot-provision.sh" ]]; then
  PROVISION_HELPER="${APP_DIR}/deploy/oracle/oc-certbot-provision.sh"
fi
if [[ -n "${PROVISION_HELPER}" ]]; then
  install -o root -g root -m 755 "${PROVISION_HELPER}" /usr/local/bin/oc-certbot-provision
else
  echo "==> Downloading shared certbot provision helper"
  curl -fsSL "${REPO%.git}/raw/main/deploy/oracle/oc-certbot-provision.sh" \
    -o /usr/local/bin/oc-certbot-provision
  chown root:root /usr/local/bin/oc-certbot-provision
  chmod 755 /usr/local/bin/oc-certbot-provision
fi

echo "==> Provisioning TLS for ${NIP_DOMAIN}"
/usr/local/bin/oc-certbot-provision "${NIP_DOMAIN}" "${CERTBOT_EMAIL}"
echo "==> TLS active for ${NIP_DOMAIN}"

# ---------------------------------------------------------------------------
# 4 — Enable automatic renewal (once daily, no-op until 30 days before expiry)
# ---------------------------------------------------------------------------
if systemctl list-unit-files --no-legend certbot.timer 2>/dev/null | grep -q '^certbot\.timer'; then
  systemctl enable --now certbot.timer
  echo "==> certbot.timer enabled (systemd)"
else
  if ! command -v crontab > /dev/null 2>&1; then
    echo "==> Installing cron for renewal fallback"
    _apt_install cron
  fi
  # Use the same deploy-user crontab and entry format as deploy.sh so both
  # scripts share a single renewal job and duplicate detection works correctly.
  DEPLOY_CRON_JOB="0 3 * * * sudo /usr/bin/certbot renew --quiet"
  existing_cron="$(crontab -l -u "${APP_USER}" 2>/dev/null || true)"
  if echo "${existing_cron}" | grep -qFx "${DEPLOY_CRON_JOB}"; then
    echo "==> certbot renewal cron already present for deploy user"
  else
    (
      echo "${existing_cron}" \
        | grep -vFx "0 3 * * * certbot renew --quiet" \
        | grep -vFx "0 3 * * * /usr/bin/certbot renew --quiet" \
        | grep -vFx "${DEPLOY_CRON_JOB}" \
        || true
      echo "${DEPLOY_CRON_JOB}"
    ) | crontab -u "${APP_USER}" -
    echo "==> Daily certbot renewal cron installed for ${APP_USER} (03:00)"
  fi
fi

echo ""
echo "Done. TLS is active for https://${NIP_DOMAIN}"
echo "Set VITE_API_BASE=https://${NIP_DOMAIN} in GitHub Actions secrets."
