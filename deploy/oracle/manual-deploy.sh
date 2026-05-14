#!/usr/bin/env bash
# Mirrors the GitHub Actions backend-deploy job for local testing.
# Reads secrets from .env.deploy (not committed — see .env.deploy.example).
#
# Usage:
#   cp deploy/oracle/.env.deploy.example deploy/oracle/.env.deploy
#   # fill in OCI_USER, OCI_HOST, OCI_SSH_KEY_FILE, OCI_KNOWN_HOSTS
#   bash deploy/oracle/manual-deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.deploy"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found." >&2
  echo "       Copy .env.deploy.example and fill in the values." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

: "${OCI_USER:?OCI_USER must be set in ${ENV_FILE}}"
: "${OCI_HOST:?OCI_HOST must be set in ${ENV_FILE}}"
: "${OCI_SSH_KEY_FILE:?OCI_SSH_KEY_FILE must be set in ${ENV_FILE}}"

echo "==> Building minimal backend archive"
ARCHIVE="/tmp/orthodox-calendar-backend.tar.gz"
tar -czf "${ARCHIVE}" \
    -C "${REPO_ROOT}" \
    --exclude='*/__pycache__' \
    --exclude='*.py[co]' \
    backend/app \
    backend/requirements.txt
echo "    Archive: ${ARCHIVE} ($(du -sh "${ARCHIVE}" | cut -f1))"

echo "==> Uploading archive to ${OCI_USER}@${OCI_HOST}"
scp -i "${OCI_SSH_KEY_FILE}" \
    -o BatchMode=yes \
    -o ConnectTimeout=15 \
    -o StrictHostKeyChecking=accept-new \
    "${ARCHIVE}" \
    "${OCI_USER}@${OCI_HOST}:/tmp/orthodox-calendar-backend.tar.gz"

echo "==> Running deploy.sh on Oracle VM"
ssh -i "${OCI_SSH_KEY_FILE}" \
    -o BatchMode=yes \
    -o ConnectTimeout=15 \
    -o StrictHostKeyChecking=accept-new \
    "${OCI_USER}@${OCI_HOST}" \
    'APP_DIR=/home/'"${OCI_USER}"'/orthodox-calendar RELEASE_ARCHIVE=/tmp/orthodox-calendar-backend.tar.gz bash -s' \
    < "${SCRIPT_DIR}/deploy.sh"

echo ""
echo "==> Done. Backend deployed to ${OCI_HOST}."
