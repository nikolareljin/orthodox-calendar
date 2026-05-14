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
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"
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

APP_USER="$(id -un)"

# Install systemd service unit if missing or stale
UNIT_FILE="/etc/systemd/system/${SERVICE}.service"
if [[ ! -f "${UNIT_FILE}" ]]; then
  echo "==> Installing systemd service unit"
  sudo tee "${UNIT_FILE}" > /dev/null <<UNIT
[Unit]
Description=Orthodox Calendar — FastAPI backend
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="ORTHODOX_CALENDAR_DATA_PATH=${APP_DIR}/backend/app/data"
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app \\
          --host 127.0.0.1 --port 8000 \\
          --workers 2 \\
          --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE}"
fi

# Install nginx site config if missing
NGINX_SITE="/etc/nginx/sites-available/${SERVICE}"
if [[ ! -f "${NGINX_SITE}" ]]; then
  echo "==> Installing nginx site config"
  sudo tee "${NGINX_SITE}" > /dev/null <<'NGINXCONF'
server {
    listen 80;
    listen [::]:80;
    server_name _;

    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    location = /nginx-health {
        access_log off;
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
NGINXCONF
  sudo ln -sf "${NGINX_SITE}" "/etc/nginx/sites-enabled/${SERVICE}"
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo systemctl restart nginx
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
