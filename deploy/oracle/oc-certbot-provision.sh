#!/usr/bin/env bash
# Usage: oc-certbot-provision <nip-domain> <email>
# Installed by setup.sh/setup-tls.sh; run as root or through sudo.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: oc-certbot-provision <nip-domain> <email>" >&2
  exit 1
fi
DOMAIN="$1"
EMAIL="$2"

# Validate domain is a well-formed nip.io hostname derived from an IPv4 address.
# Rejects anything with spaces, shell metacharacters, or nginx config syntax.
_nip_re='^[0-9]+-[0-9]+-[0-9]+-[0-9]+\.nip\.io$'
_valid_ipv4_re='^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
DOMAIN_IP="${DOMAIN%.nip.io}"
DOMAIN_IP="${DOMAIN_IP//-/.}"
if ! [[ "${DOMAIN}" =~ ${_nip_re} ]] || ! [[ "${DOMAIN_IP}" =~ ${_valid_ipv4_re} ]]; then
  echo "ERROR: oc-certbot-provision: '${DOMAIN}' is not a valid nip.io hostname" >&2
  exit 1
fi

NGINX_SITE="/etc/nginx/sites-available/orthodox-calendar"
# Update server_name before certbot so --nginx can match this vhost by name.
if [[ ! -f "${NGINX_SITE}" ]]; then
  echo "ERROR: oc-certbot-provision: nginx site ${NGINX_SITE} not found" >&2
  exit 1
fi

NGINX_SITE_BACKUP="$(mktemp)"
cp "${NGINX_SITE}" "${NGINX_SITE_BACKUP}"
restore_nginx_site() {
  cp "${NGINX_SITE_BACKUP}" "${NGINX_SITE}"
  if nginx -t >/dev/null 2>&1; then
    if systemctl is-active --quiet nginx 2>/dev/null; then
      systemctl reload nginx || true
    fi
  fi
  rm -f "${NGINX_SITE_BACKUP}"
}
cleanup_nginx_backup() {
  rm -f "${NGINX_SITE_BACKUP}"
}
rollback_nginx_site() {
  local reason="$1"
  restore_nginx_site
  trap - EXIT
  echo "ERROR: oc-certbot-provision: ${reason}; restored previous nginx site config" >&2
  exit 1
}
trap cleanup_nginx_backup EXIT

_prune_missing_ssl_refs() {
  local missing=false path
  while IFS= read -r path; do
    if [[ -n "${path}" && ! -e "${path}" ]]; then
      missing=true
      break
    fi
  done < <(
    sed -n 's/^[[:space:]]*ssl_certificate[[:space:]]\+\([^;]*\);.*/\1/p' "${NGINX_SITE}"
    sed -n 's/^[[:space:]]*ssl_certificate_key[[:space:]]\+\([^;]*\);.*/\1/p' "${NGINX_SITE}"
    sed -n 's/^[[:space:]]*include[[:space:]]\+\(\/etc\/letsencrypt\/options-ssl-nginx\.conf\);.*/\1/p' "${NGINX_SITE}"
    sed -n 's/^[[:space:]]*ssl_dhparam[[:space:]]\+\(\/etc\/letsencrypt\/ssl-dhparams\.pem\);.*/\1/p' "${NGINX_SITE}"
  )
  if [[ "${missing}" == "true" ]]; then
    sed -i \
      -e '/^[[:space:]]*ssl_certificate[[:space:]]/d' \
      -e '/^[[:space:]]*ssl_certificate_key[[:space:]]/d' \
      -e '/^[[:space:]]*include[[:space:]]*\/etc\/letsencrypt\/options-ssl-nginx\.conf/d' \
      -e '/^[[:space:]]*ssl_dhparam[[:space:]]*\/etc\/letsencrypt\/ssl-dhparams\.pem/d' \
      -e 's/listen \([^;]*\) ssl/listen \1/g' \
      "${NGINX_SITE}"
  fi
}

_set_nip_domain() {
  sed -i \
    -e "s/server_name[[:space:]]\+[^;]*;/server_name ${DOMAIN};/g" \
    -e "s/if ([\$]host = [0-9]\+-[0-9]\+-[0-9]\+-[0-9]\+\.nip\.io)/if (\$host = ${DOMAIN})/g" \
    "${NGINX_SITE}"
}

_set_nip_domain
_prune_missing_ssl_refs
nginx -t || rollback_nginx_site "nginx validation failed"
if ! systemctl is-active --quiet nginx 2>/dev/null; then
  systemctl enable nginx || rollback_nginx_site "nginx enable failed"
  systemctl start nginx || rollback_nginx_site "nginx start failed"
fi

CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [[ -f "${CERT_PATH}" ]] && grep -qF "/etc/letsencrypt/live/${DOMAIN}/" "${NGINX_SITE}" 2>/dev/null; then
  if ! certbot renew --quiet --cert-name "${DOMAIN}"; then
    echo "    certbot renew failed (renewal config may be broken); attempting fresh provisioning"
    if ! certbot --nginx \
      -d "${DOMAIN}" \
      --non-interactive \
      --agree-tos \
      -m "${EMAIL}" \
      --redirect; then
      rollback_nginx_site "certbot failed"
    fi
  fi
else
  if ! certbot --nginx \
    -d "${DOMAIN}" \
    --non-interactive \
    --agree-tos \
    -m "${EMAIL}" \
    --redirect; then
    rollback_nginx_site "certbot failed"
  fi
fi

nginx -t || rollback_nginx_site "nginx validation failed after certbot"
systemctl reload nginx || rollback_nginx_site "nginx reload failed"
trap - EXIT
cleanup_nginx_backup
