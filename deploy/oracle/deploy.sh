#!/usr/bin/env bash
# Called by GitHub Actions over SSH to deploy a new backend version.
# Must be idempotent — safe to run multiple times.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/orthodox-calendar}"
SERVICE="orthodox-calendar"

echo "==> Pulling latest code"
cd "${APP_DIR}"
git fetch origin main
git reset --hard origin/main

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
