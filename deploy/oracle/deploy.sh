#!/usr/bin/env bash
# Called by GitHub Actions over SSH to deploy a new backend version.
# Must be idempotent — safe to run multiple times.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/orthodox-calendar}"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:-}"
SERVICE="orthodox-calendar"

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
  if ! command -v python3.12 > /dev/null 2>&1; then
    echo "ERROR: python3.12 is required but not found — run deploy/oracle/setup.sh on the server first" >&2
    exit 1
  fi
  rm -rf .venv
  if ! python3.12 -m venv .venv; then
    echo "ERROR: python3.12 -m venv failed — ensure python3.12-venv is installed (run setup.sh)" >&2
    exit 1
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
