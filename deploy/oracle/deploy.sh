#!/usr/bin/env bash
# Called by GitHub Actions over SSH to deploy a new backend version.
# Prerequisite: deploy/oracle/setup.sh must have been run on the server first.
# Must be idempotent — safe to run multiple times.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/orthodox-calendar}"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:-}"
SERVICE="orthodox-calendar"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

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
_pkg_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -qx 'install ok installed'
}
_ensure_certbot_packages() {
  if ! command -v certbot > /dev/null 2>&1; then
    _apt_install certbot
  fi
  if ! _pkg_installed python3-certbot-nginx; then
    _apt_install python3-certbot-nginx
  fi
}
_ensure_nginx_running() {
  if systemctl is-active --quiet nginx 2>/dev/null; then
    return 0
  fi
  sudo systemctl enable nginx && sudo systemctl start nginx
}
_repair_tls_with_provisioner() {
  local domain="$1"
  if [[ -z "${CERTBOT_EMAIL}" ]]; then
    echo "ERROR: CERTBOT_EMAIL is not set." >&2
    echo "       Set it so deploy.sh can repair/re-provision the broken HTTPS endpoint." >&2
    return 1
  fi
  if [[ ! -x "/usr/local/bin/oc-certbot-provision" ]]; then
    echo "ERROR: /usr/local/bin/oc-certbot-provision not found." >&2
    echo "       deploy.sh cannot repair stale nginx TLS references without the setup.sh wrapper." >&2
    return 1
  fi
  sudo /usr/local/bin/oc-certbot-provision "${domain}" "${CERTBOT_EMAIL}"
}

echo "==> Pre-flight checks"
# Check setup.sh artifacts first — fail fast before any apt operations on an
# unprepared VM (avoids misleading sudo/apt errors masking the real cause).
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
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/${SERVICE}"
if [[ ! -L "${NGINX_SITE_ENABLED}" ]]; then
  echo "ERROR: nginx sites-enabled symlink ${NGINX_SITE_ENABLED} not found." >&2
  echo "       Run deploy/oracle/setup.sh on the server first." >&2
  exit 1
fi

if ! command -v curl > /dev/null 2>&1; then
  _apt_install curl
fi
if ! command -v python3.12 > /dev/null 2>&1; then
  echo "ERROR: python3.12 is required but not found — run deploy/oracle/setup.sh on the server first" >&2
  exit 1
fi
if ! _pkg_installed python3.12-venv; then
  _apt_install python3.12-venv
fi
if ! command -v nginx > /dev/null 2>&1; then
  _apt_install nginx
fi

echo "==> Detecting public IP"
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
_raw="$(curl -sf --max-time 5 -H 'Authorization: Bearer Oracle' 'http://169.254.169.254/opc/v2/vnics/' 2>/dev/null || true)"
PUBLIC_IP="$(echo "${_raw}" | python3.12 -c 'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' 2>/dev/null || true)"
if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
  PUBLIC_IP=""
fi
if [[ -z "${PUBLIC_IP}" ]]; then
  _raw="$(curl -sf --max-time 5 'http://169.254.169.254/opc/v1/vnics/' 2>/dev/null || true)"
  PUBLIC_IP="$(echo "${_raw}" | python3.12 -c 'import sys,json; d=json.load(sys.stdin); print(d[0].get("publicIp",""))' 2>/dev/null || true)"
  if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
    PUBLIC_IP=""
  fi
fi
if [[ -z "${PUBLIC_IP}" ]]; then
  PUBLIC_IP="$(curl -sf --max-time 10 https://ifconfig.me 2>/dev/null || true)"
fi
unset _raw
# Validate before use — reject anything that is not a plain IPv4 address to
# prevent nginx config injection from a malformed or intercepted HTTP response.
if [[ -n "${PUBLIC_IP}" ]] && ! [[ "${PUBLIC_IP}" =~ ${_valid_ipv4_re} ]]; then
  echo "    WARNING: detected value '${PUBLIC_IP}' is not a valid IPv4 address — ignoring"
  PUBLIC_IP=""
fi
NIP_DOMAIN=""
MANAGED_NIP_TLS=false
if [[ -n "${PUBLIC_IP}" ]]; then
  NIP_DOMAIN="${PUBLIC_IP//./-}.nip.io"
  echo "    Public IP: ${PUBLIC_IP} → ${NIP_DOMAIN}"
else
  echo "    Could not detect public IP — skipping TLS step"
fi

if [[ -n "${NIP_DOMAIN}" ]]; then
  # Nginx config referencing the domain cert is the reliable TLS-active signal.
  # The cert file lives under root-only /etc/letsencrypt/live — the deploy user
  # cannot stat it, so we rely on nginx having the path configured instead.
  # Also verify nginx references the cert for THIS domain, not a stale old IP.
  # Before trusting an existing TLS config, run the due-only renewal path so
  # expired/near-expiry certs are repaired before the backend goes live.
  if grep -qF "/etc/letsencrypt/live/${NIP_DOMAIN}/" "${NGINX_SITE}" 2>/dev/null; then
    if [[ -x "/usr/local/bin/oc-certbot-renew" ]]; then
      _ensure_certbot_packages
      if ! _ensure_nginx_running; then
        echo "    nginx failed to start with existing TLS config; attempting repair via certbot wrapper"
        if ! _repair_tls_with_provisioner "${NIP_DOMAIN}"; then
          echo "ERROR: TLS repair failed for existing config." >&2
          echo "       Fix certbot/nginx and redeploy before publishing the frontend." >&2
          exit 1
        fi
      elif ! sudo /usr/local/bin/oc-certbot-renew "${NIP_DOMAIN}"; then
        echo "    certbot renewal failed (certs may be corrupted/deleted); attempting repair via provisioner"
        if ! _repair_tls_with_provisioner "${NIP_DOMAIN}"; then
          echo "ERROR: TLS repair failed after failed renewal." >&2
          echo "       Fix certbot/nginx and redeploy before publishing the frontend." >&2
          exit 1
        fi
      fi
    else
      echo "    WARNING: oc-certbot-renew wrapper missing; skipping deploy-time renewal check."
      echo "             Re-run setup.sh when convenient to install the scoped renewal wrapper."
    fi
    echo "==> TLS already active for ${NIP_DOMAIN}"
    MANAGED_NIP_TLS=true
  elif grep -q 'ssl_certificate' "${NGINX_SITE}" 2>/dev/null \
      && ! grep -Eq '/etc/letsencrypt/live/[0-9]+-[0-9]+-[0-9]+-[0-9]+\.nip\.io/' "${NGINX_SITE}" 2>/dev/null; then
    echo "==> Existing custom TLS config detected; leaving nginx server_name/certificate unchanged"
  else
    echo "==> Obtaining TLS certificate for ${NIP_DOMAIN}"
    # CERTBOT_EMAIL and the oc-certbot-provision wrapper are only required when
    # actually provisioning a new certificate, not on routine redeploys where TLS
    # is already active. Checking them here avoids breaking existing-cert deploys.
    if [[ -z "${CERTBOT_EMAIL}" ]]; then
      echo "ERROR: CERTBOT_EMAIL is not set." >&2
      echo "       Set the CERTBOT_EMAIL GitHub secret before deploying the HTTPS API endpoint." >&2
      exit 1
    fi
    if [[ ! -x "/usr/local/bin/oc-certbot-provision" ]]; then
      echo "ERROR: /usr/local/bin/oc-certbot-provision not found." >&2
      echo "       deploy.sh prunes the repo checkout, so restore the full clone before" >&2
      echo "       rerunning setup.sh, or run the documented initial setup flow again." >&2
      exit 1
    fi
    _ensure_certbot_packages
    # oc-certbot-provision updates server_name then calls certbot with fixed flags.
    # Root-owned wrapper installed by setup.sh — no wildcard injection surface.
    if sudo /usr/local/bin/oc-certbot-provision "${NIP_DOMAIN}" "${CERTBOT_EMAIL}"; then
      echo "    Certificate obtained. Backend available at https://${NIP_DOMAIN}"
      MANAGED_NIP_TLS=true
    else
      echo "ERROR: TLS provisioning failed for https://${NIP_DOMAIN}." >&2
      echo "       Fix the certbot/nginx issue and redeploy before publishing the frontend." >&2
      exit 1
    fi
  fi
fi

# Enable automatic cert renewal only when TLS is active on this VM.
# Skipped when NIP_DOMAIN is empty (no public IP detected, TLS not used).
if [[ "${MANAGED_NIP_TLS}" == "true" ]]; then
  # certbot renew is a no-op until 30 days before expiry, so a daily check is
  # fine. Prefer the systemd timer when present; fall back to a deploy-user cron
  # only when the timer unit is absent from the system.
  # A sudoers failure enabling the timer means the server needs setup.sh rerun —
  # do not install cron in that case, as the cron sudo entry is also absent.
  if systemctl list-unit-files --no-legend certbot.timer 2>/dev/null | grep -q '^certbot\.timer'; then
    if systemctl is-active --quiet certbot.timer 2>/dev/null \
        && systemctl is-enabled --quiet certbot.timer 2>/dev/null; then
      echo "==> certbot.timer already active and enabled"
    elif sudo systemctl enable --now certbot.timer 2>/dev/null; then
      echo "==> certbot.timer enabled for automatic renewal"
    else
      echo "ERROR: certbot.timer exists but could not be enabled." >&2
      echo "       Re-run deploy/oracle/setup.sh to update sudoers/systemd, then redeploy." >&2
      exit 1
    fi
    # Remove stale deploy-user certbot cron entries now that the timer manages renewal.
    _stale_cron="$(crontab -l 2>/dev/null || true)"
    if echo "${_stale_cron}" | grep -qE 'certbot renew|oc-certbot-renew'; then
      (
        echo "${_stale_cron}" \
          | grep -vFx "0 3 * * * certbot renew --quiet" \
          | grep -vFx "0 3 * * * /usr/bin/certbot renew --quiet" \
          | grep -vFx "0 3 * * * sudo /usr/bin/certbot renew --quiet" \
          | grep -vE "^0 3 \* \* \* sudo /usr/local/bin/oc-certbot-renew " \
          || true
      ) | crontab -
      echo "==> Removed stale certbot cron from deploy user crontab"
    fi
    # Also remove the root-owned /etc/cron.d fallback installed by setup-tls.sh.
    if [[ -f "/etc/cron.d/orthodox-calendar-certbot" ]]; then
      sudo rm -f /etc/cron.d/orthodox-calendar-certbot 2>/dev/null \
        && echo "==> Removed stale /etc/cron.d certbot cron" \
        || echo "    WARNING: could not remove /etc/cron.d/orthodox-calendar-certbot; re-run setup.sh."
    fi
  else
    if ! command -v crontab > /dev/null 2>&1; then
      echo "ERROR: certbot.timer is absent and crontab is not installed." >&2
      echo "       Re-run setup.sh to install cron, then redeploy." >&2
      exit 1
    fi
    _CRON_D_FILE="/etc/cron.d/orthodox-calendar-certbot"
    _CRON_D_LINE="0 3 * * * root /usr/bin/certbot renew --quiet"
    if [[ -f "${_CRON_D_FILE}" ]] && grep -qFx "${_CRON_D_LINE}" "${_CRON_D_FILE}" 2>/dev/null; then
      echo "==> certbot renewal already managed via ${_CRON_D_FILE}"
      # Remove stale deploy-user certbot cron entries that may coexist.
      _existing_user_cron="$(crontab -l 2>/dev/null || true)"
      if echo "${_existing_user_cron}" | grep -qE 'certbot renew|oc-certbot-renew'; then
        (
          echo "${_existing_user_cron}" \
            | grep -vFx "0 3 * * * certbot renew --quiet" \
            | grep -vFx "0 3 * * * /usr/bin/certbot renew --quiet" \
            | grep -vFx "0 3 * * * sudo /usr/bin/certbot renew --quiet" \
            | grep -vE "^0 3 \* \* \* sudo /usr/local/bin/oc-certbot-renew " \
            || true
        ) | crontab -
        echo "==> Removed stale certbot cron from deploy user crontab"
      fi
    elif [[ ! -x "/usr/local/bin/oc-certbot-renew" ]]; then
      echo "    WARNING: oc-certbot-renew wrapper missing; skipping renewal cron installation."
      echo "             Re-run deploy/oracle/setup.sh to install the wrapper and renewal job."
    else
      CRON_JOB="0 3 * * * sudo /usr/local/bin/oc-certbot-renew ${NIP_DOMAIN}"
      existing_cron="$(crontab -l 2>/dev/null || true)"
      if echo "${existing_cron}" | grep -qFx "${CRON_JOB}"; then
        echo "==> Daily certbot renewal cron already present"
      else
        (
          echo "${existing_cron}" \
            | grep -vFx "0 3 * * * certbot renew --quiet" \
            | grep -vFx "0 3 * * * /usr/bin/certbot renew --quiet" \
            | grep -vFx "0 3 * * * sudo /usr/bin/certbot renew --quiet" \
            | grep -vFx "${CRON_JOB}" \
            || true
          echo "${CRON_JOB}"
        ) | crontab -
        echo "==> Daily certbot renewal cron installed/updated (03:00)"
      fi
    fi
  fi
fi

if ! systemctl is-active --quiet nginx 2>/dev/null; then
  sudo systemctl enable nginx
  sudo systemctl start nginx
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
