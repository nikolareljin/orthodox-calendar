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
: "${OCI_KNOWN_HOSTS:?OCI_KNOWN_HOSTS must be set in ${ENV_FILE}}"

KNOWN_HOSTS_FILE="$(mktemp)"
printf '%s\n' "${OCI_KNOWN_HOSTS}" > "${KNOWN_HOSTS_FILE}"
trap 'rm -f "${KNOWN_HOSTS_FILE}"' EXIT

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
    -o UserKnownHostsFile="${KNOWN_HOSTS_FILE}" \
    -o StrictHostKeyChecking=yes \
    "${ARCHIVE}" \
    "${OCI_USER}@${OCI_HOST}:/tmp/orthodox-calendar-backend.tar.gz"

echo "==> Running deploy.sh on Oracle VM"
_deploy_env="APP_DIR=/home/${OCI_USER}/orthodox-calendar RELEASE_ARCHIVE=/tmp/orthodox-calendar-backend.tar.gz"
if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
  printf -v _email_q '%q' "${CERTBOT_EMAIL}"
  _deploy_env="${_deploy_env} CERTBOT_EMAIL=${_email_q}"
fi
ssh -i "${OCI_SSH_KEY_FILE}" \
    -o BatchMode=yes \
    -o ConnectTimeout=15 \
    -o UserKnownHostsFile="${KNOWN_HOSTS_FILE}" \
    -o StrictHostKeyChecking=yes \
    "${OCI_USER}@${OCI_HOST}" \
    "${_deploy_env} bash -s" \
    < "${SCRIPT_DIR}/deploy.sh"

echo ""
echo "==> Done. Backend deployed to ${OCI_HOST}."
