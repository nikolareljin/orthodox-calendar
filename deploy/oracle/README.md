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
curl http://<YOUR_VM_IP>/docs            # FastAPI Swagger UI
```

### Optional — TLS with Let's Encrypt

Point a domain (e.g. `api.orthodox-calendar.org`) at the VM IP, then:

```bash
sudo certbot --nginx -d api.orthodox-calendar.org
```

Certbot auto-renews via its own systemd timer. Once HTTPS is live, set
`VITE_API_BASE=https://api.orthodox-calendar.org` in GitHub secrets.

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
   - **Backend** — SSH into the Oracle VM, runs `deploy/oracle/deploy.sh` (git pull + pip install + systemctl restart), then health-checks the service.

---

## 5 — Manual deployment

If you need to deploy without a CI run:

```bash
ssh ubuntu@<YOUR_VM_IP> 'APP_DIR=/home/ubuntu/orthodox-calendar bash -s' < deploy/oracle/deploy.sh
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
