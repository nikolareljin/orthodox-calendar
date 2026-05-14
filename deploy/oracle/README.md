# Oracle Cloud Always Free — backend deployment

This directory contains everything needed to run the FastAPI backend on an Oracle Cloud
Always Free VM. The frontend is deployed separately to GitHub Pages via the CI workflow.

---

## Architecture

```
GitHub Pages                    Oracle Cloud Always Free VM
──────────────────              ──────────────────────────────────────────
React SPA (static)              nginx (port 80 / 443)
   │                               │
   │  VITE_API_BASE=               │  reverse proxy
   └──────────────────────────►  uvicorn (127.0.0.1:8000)
                                   │
                                   └──  FastAPI app
                                         └──  app/data/*.json (saints data)
```

---

## 1 — Create the Oracle Cloud VM

1. Log in to [cloud.oracle.com](https://cloud.oracle.com).
2. **Compute → Instances → Create Instance**.
3. Choose:
   - **Shape:** `VM.Standard.E2.1.Micro` (AMD, Always Free) or `VM.Standard.A1.Flex` (Ampere ARM, Always Free — 4 OCPUs / 24 GB if kept within always-free limits)
   - **Image:** Ubuntu 22.04 LTS (Minimal)
   - **SSH keys:** paste your public key (you will need the matching private key for GitHub secrets)
4. Note the **Public IP address** once the instance is running.

### Open ports in the VCN Security List

Compute → Instances → your instance → VCN → Security Lists → Default Security List:

| Direction | Protocol | Port range | Source |
|-----------|----------|------------|--------|
| Ingress   | TCP      | 80         | 0.0.0.0/0 |
| Ingress   | TCP      | 443        | 0.0.0.0/0 |

---

## 2 — Initial server setup (run once)

SSH into the VM:

```bash
ssh ubuntu@<YOUR_VM_IP>
```

Then run the setup script (it installs Python, nginx, the systemd service, and opens OS-level firewall ports):

```bash
curl -fsSL https://raw.githubusercontent.com/nikolareljin/orthodox-calendar/main/deploy/oracle/setup.sh | sudo bash
```

Verify:

```bash
curl http://localhost:8000/health        # should return {"status":"ok"}
curl http://<YOUR_VM_IP>/api/v1/docs     # FastAPI Swagger UI
```

### TLS with Let's Encrypt (nip.io)

No domain registration needed. The `setup-tls.sh` script uses **nip.io** — a
wildcard DNS service that maps `<dashed-ip>.nip.io` to the same IP automatically
(e.g. `1-2-3-4.nip.io` → `1.2.3.4`). Run it once on the VM:

```bash
# setup.sh clones the repo to ~/orthodox-calendar; use the absolute path:
sudo bash ~/orthodox-calendar/deploy/oracle/setup-tls.sh
# — or from inside the cloned repo directory:
sudo bash deploy/oracle/setup-tls.sh
```

What the script does:

1. Auto-detects the public IP from the Oracle IMDS (or `ifconfig.me` fallback).
2. Installs `certbot` + `python3-certbot-nginx` if absent.
3. Issues a certificate for `<dashed-ip>.nip.io` via `certbot --nginx` (skips if
   already present).
4. Enables automatic renewal — prefers the `certbot.timer` systemd unit that
   `apt` installs; falls back to a single daily cron entry at 03:00. Certbot
   contacts Let's Encrypt **only when the cert is within 30 days of expiry**, so
   the check is cheap.

**Options:**

| Flag | Default | Purpose |
|------|---------|---------|
| `--ip <address>` | auto-detected | Override the public IP |
| `--email <address>` | `nikola.reljin@gmail.com` | Let's Encrypt expiry notifications |

Once HTTPS is live the script prints the `VITE_API_BASE` value to set in
GitHub Actions secrets:

```
Done. TLS is active for https://1-2-3-4.nip.io
Set VITE_API_BASE=https://1-2-3-4.nip.io in GitHub Actions secrets.
```

> **Note:** if the Oracle VM is ever reprovisioned with a new public IP, re-run
> `setup-tls.sh` — it will detect the new IP, update the nginx `server_name` to
> the new nip.io hostname, and obtain a fresh certificate automatically.

---

## 3 — GitHub secrets

Go to **github.com/nikolareljin/orthodox-calendar → Settings → Secrets and variables → Actions**
and add:

| Secret | Value |
|--------|-------|
| `OCI_HOST` | Public IP (or domain) of the Oracle VM |
| `OCI_USER` | `ubuntu` (Ubuntu images) or `opc` (Oracle Linux) |
| `OCI_SSH_KEY` | Contents of the **private** SSH key that matches the public key on the VM |
| `OCI_KNOWN_HOSTS` | Output of: `ssh-keyscan -H <YOUR_VM_IP>` run from your laptop |
| `VITE_API_BASE` | `http://<YOUR_VM_IP>` (or `https://your.domain.com` after TLS) |

Generate `OCI_KNOWN_HOSTS` on your machine (not the VM):

```bash
ssh-keyscan -H <YOUR_VM_IP>
```

Copy the full output (one or more lines) as the secret value.

### Enable GitHub Pages

Settings → Pages → Source: **GitHub Actions** (not a branch).

---

## 4 — How deployment works

On every merge of a `release/x.y.z` branch into `main`:

1. **Security gate** — gitleaks + data-safety check (must pass before anything deploys).
2. **Auto-tag** — creates the version tag from the branch name.
3. In parallel:
   - **Frontend** — built with `VITE_BASE=/orthodox-calendar/` and `VITE_API_BASE` from secrets, published to GitHub Pages.
   - **Backend** — uploads a minimal archive containing only `backend/app` and `backend/requirements.txt`, prunes older non-runtime files from the app directory, runs `deploy/oracle/deploy.sh` (pip install + systemctl restart), then health-checks the service.

---

## 5 — Manual deployment

If you need to deploy without a CI run:

```bash
tar -czf /tmp/orthodox-calendar-backend.tar.gz \
  --exclude='*/__pycache__' \
  --exclude='*.py[co]' \
  backend/app \
  backend/requirements.txt
scp /tmp/orthodox-calendar-backend.tar.gz ubuntu@<YOUR_VM_IP>:/tmp/orthodox-calendar-backend.tar.gz
ssh ubuntu@<YOUR_VM_IP> \
  'APP_DIR=/home/ubuntu/orthodox-calendar RELEASE_ARCHIVE=/tmp/orthodox-calendar-backend.tar.gz bash -s' \
  < deploy/oracle/deploy.sh
```

---

## Troubleshooting

```bash
# Service logs
sudo journalctl -u orthodox-calendar -f

# Restart manually
sudo systemctl restart orthodox-calendar

# Test health
curl http://localhost:8000/health

# nginx logs
sudo tail -f /var/log/nginx/error.log
```
