#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

VENV="$REPO_ROOT/.venv-import"

echo "=== Setting up virtual environment ==="
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "=== Installing import dependencies ==="
pip install --quiet -r scripts/requirements-import.txt

echo "=== Installing Playwright Chromium ==="
playwright install chromium

echo "=== Scraping GOARCH chapel calendar (headed browser — interact if CF challenge appears) ==="
python3 scripts/import_goarch.py \
    --no-headless \
    --year 2024 \
    --delay 2.0 \
    --out scripts/goarch_raw.json

echo ""
echo "=== Enriching OCA + Greek datasets with GOARCH URLs ==="
python3 scripts/enrich_goarch.py \
    --goarch scripts/goarch_raw.json \
    --oca    backend/app/data/oca_julian.json \
    --greek  backend/app/data/traditions/greek_saints.json \
    --fetch-notes \
    --delay 1.5

echo ""
echo "=== Verification ==="
python3 - <<'EOF'
import json, pathlib

raw = json.loads(pathlib.Path("scripts/goarch_raw.json").read_text())
days  = len(raw)
total = sum(len(v) for v in raw.values())
print(f"goarch_raw.json  : {days} days, {total} saints")

oca = json.loads(pathlib.Path("backend/app/data/oca_julian.json").read_text())
enriched = sum(
    1 for e in oca for s in e.get("saints", []) if s.get("goarch_url")
)
print(f"oca_julian.json  : {enriched} saints now have goarch_url")

greek = json.loads(pathlib.Path("backend/app/data/traditions/greek_saints.json").read_text())
total_greek = sum(len(e.get("saints", [])) for e in greek)
print(f"greek_saints.json: {total_greek} saints total")
EOF

echo ""
echo "=== Done. Add HAGIOGRAPHY_SOURCE=goarch to .env to activate GOARCH URLs in the API. ==="
