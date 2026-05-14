#!/usr/bin/env bash
# setup-tls.sh — obtain a Let's Encrypt TLS certificate via nip.io and enable
# automatic renewal. Safe to run multiple times (idempotent).
#
# Usage:
#   sudo bash setup-tls.sh
#   sudo bash setup-tls.sh --ip 1.2.3.4       # override auto-detected IP
#   sudo bash setup-tls.sh --email you@x.com  # override notification address
#
# nip.io maps <dashed-ip>.nip.io → the same IP automatically, so no domain
# registration is needed. Certificates are valid for 90 days; this script also
# installs a once-daily renewal check (no-op until 30 days before expiry).
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
CERTBOT_EMAIL="nikola.reljin@gmail.com"
FORCED_IP=""

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

# ---------------------------------------------------------------------------
# 1 — Resolve public IP → nip.io domain
# ---------------------------------------------------------------------------
if [[ -n "${FORCED_IP}" ]]; then
  PUBLIC_IP="${FORCED_IP}"
else
  echo "==> Detecting public IP"
  _raw="$(curl -sf --max-time 5 -H 'Authorization: Bearer Oracle' \
    'http://169.254.169.254/opc/v2/vnics/' 2>/dev/null || true)"
  PUBLIC_IP="$(echo "${_raw}" | python3 -c \
    'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' \
    2>/dev/null || true)"
  if [[ -z "${PUBLIC_IP}" ]]; then
    _raw="$(curl -sf --max-time 5 'http://169.254.169.254/opc/v1/vnics/' 2>/dev/null || true)"
    PUBLIC_IP="$(echo "${_raw}" | python3 -c \
      'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' \
      2>/dev/null || true)"
  fi
  if [[ -z "${PUBLIC_IP}" ]]; then
    PUBLIC_IP="$(curl -sf --max-time 10 ifconfig.me 2>/dev/null || true)"
  fi
  unset _raw
fi

if [[ -z "${PUBLIC_IP}" ]]; then
  echo "ERROR: could not determine public IP. Pass it with --ip <address>." >&2
  exit 1
fi

NIP_DOMAIN="${PUBLIC_IP//./-}.nip.io"
echo "==> IP: ${PUBLIC_IP}  →  domain: ${NIP_DOMAIN}"

# ---------------------------------------------------------------------------
# 2 — Install certbot if absent
# ---------------------------------------------------------------------------
if ! command -v certbot > /dev/null 2>&1; then
  echo "==> Installing certbot"
  _apt_install certbot
fi
if ! dpkg -s python3-certbot-nginx > /dev/null 2>&1; then
  _apt_install python3-certbot-nginx
fi

# ---------------------------------------------------------------------------
# 3 — Obtain certificate (skip if already present for this domain)
# ---------------------------------------------------------------------------
CERT_PATH="/etc/letsencrypt/live/${NIP_DOMAIN}/fullchain.pem"
if [[ -f "${CERT_PATH}" ]]; then
  echo "==> Certificate already present: ${CERT_PATH}"
else
  echo "==> Requesting certificate for ${NIP_DOMAIN}"
  certbot --nginx \
    -d "${NIP_DOMAIN}" \
    --non-interactive \
    --agree-tos \
    -m "${CERTBOT_EMAIL}" \
    --redirect
  echo "    Certificate obtained. Backend available at https://${NIP_DOMAIN}"
fi

# ---------------------------------------------------------------------------
# 4 — Enable automatic renewal (once daily, no-op until 30 days before expiry)
# ---------------------------------------------------------------------------
if systemctl list-unit-files --no-legend certbot.timer 2>/dev/null | grep -q '^certbot\.timer'; then
  systemctl enable --now certbot.timer
  echo "==> certbot.timer enabled (systemd)"
else
  CRON_JOB="0 3 * * * certbot renew --quiet"
  if crontab -l 2>/dev/null | grep -qF "certbot renew"; then
    echo "==> certbot renewal cron already present"
  else
    ( crontab -l 2>/dev/null; echo "${CRON_JOB}" ) | crontab -
    echo "==> Daily certbot renewal cron installed (03:00)"
  fi
fi

echo ""
echo "Done. TLS is active for https://${NIP_DOMAIN}"
echo "Set VITE_API_BASE=https://${NIP_DOMAIN} in GitHub Actions secrets."
