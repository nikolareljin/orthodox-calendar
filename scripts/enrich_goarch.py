#!/usr/bin/env python3
"""
Merge GOARCH chapel data into the OCA base dataset and Greek overlay.

Reads goarch_raw.json (from import_goarch.py), then for each GOARCH saint:

  MATCH found in oca_julian.json on the same MM-DD:
    → Set saint.goarch_url in oca_julian.json (fills the currently empty field)

  NO MATCH (saint unique to GOARCH / Greek EP canonization):
    → Add new entry to greek_saints.json with goarch_url populated
    → Optionally fetch hagiography text from the GOARCH saint page

Matching uses the same name normalization as backend/app/services/saints.py
(_normalize_saint_text) via scripts/_name_utils.py.

Usage:
    # Dry-run: show stats, write nothing
    python3 scripts/enrich_goarch.py --dry-run

    # Full run
    python3 scripts/enrich_goarch.py \\
        --goarch scripts/goarch_raw.json \\
        --oca    backend/app/data/oca_julian.json \\
        --greek  backend/app/data/traditions/greek_saints.json

    # Also fetch hagiography notes for new Greek saints from GOARCH pages
    python3 scripts/enrich_goarch.py --fetch-notes --delay 1.5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared name normalization (mirrors backend/app/services/saints.py)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from _name_utils import saint_keys  # noqa: E402


# ---------------------------------------------------------------------------
# Optional GOARCH page fetcher for hagiography notes
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _fetch_goarch_notes(goarch_url: str) -> str | None:
    """Fetch the first meaningful paragraph from a GOARCH saint page."""
    try:
        req = urllib.request.Request(goarch_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    WARN fetch {goarch_url}: {exc}", file=sys.stderr)
        return None

    for m in _PARA_RE.finditer(html):
        text = _TAG_RE.sub("", m.group(1)).strip()
        text = re.sub(r"\s+", " ", text)
        # Skip navigation/boilerplate paragraphs
        if len(text) > 80 and not any(w in text.lower() for w in [
            "cookie", "privacy", "copyright", "all rights", "subscribe",
            "donate", "click here", "read more",
        ]):
            return text[:400]
    return None


# ---------------------------------------------------------------------------
# Feast type detection
# ---------------------------------------------------------------------------

_FEAST_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"hieromartyr|priest.martyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr(s)?\b", re.I), "Martyr"),
    (re.compile(r"equal.to.apostle", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle(s)?\b", re.I), "Apostle"),
    (re.compile(r"prophet\b", re.I), "Prophet"),
    (re.compile(r"patriarch|metropolitan|archbishop|bishop|deacon|priest", re.I), "Hierarch"),
    (re.compile(r"\bvirgin\b", re.I), "Virgin"),
    (re.compile(r"venerable|monastic|abbot|abbess|monk", re.I), "Venerable"),
    (re.compile(r"nativity|theophany|transfiguration|ascension|pentecost|"
                r"annunciation|assumption|presentation|circumcision|"
                r"resurrection|pascha|easter|dormition|exaltation", re.I), "Great Feast"),
    (re.compile(r"great feast|feast of the lord|feast of our", re.I), "Great Feast"),
]


def _feast_type(name: str) -> str:
    for pat, ft in _FEAST_TYPE_RULES:
        if pat.search(name):
            return ft
    return "Saint"


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_oca_index(oca: list[dict]) -> dict[str, dict[str, dict]]:
    """Index: {MM-DD: {norm_key: saint_dict}} for fast lookup."""
    index: dict[str, dict[str, dict]] = {}
    for entry in oca:
        md = entry["month_day"]
        if md not in index:
            index[md] = {}
        for saint in entry.get("saints", []):
            for key in saint_keys(
                saint["name"],
                saint.get("title"),
                saint.get("hagiography_url"),
            ):
                index[md][key] = saint
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge GOARCH data into OCA + Greek datasets")
    parser.add_argument("--goarch", default="scripts/goarch_raw.json")
    parser.add_argument("--oca", default="backend/app/data/oca_julian.json")
    parser.add_argument("--greek", default="backend/app/data/traditions/greek_saints.json")
    parser.add_argument("--fetch-notes", action="store_true",
                        help="Fetch hagiography excerpt from GOARCH for unmatched saints")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between GOARCH page fetches (default 1.5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats, write nothing")
    args = parser.parse_args()

    goarch_path = Path(args.goarch)
    oca_path = Path(args.oca)
    greek_path = Path(args.greek)

    if not goarch_path.exists():
        print(f"ERROR: {goarch_path} not found. Run import_goarch.py first.", file=sys.stderr)
        sys.exit(1)

    with goarch_path.open(encoding="utf-8") as f:
        goarch_raw: dict[str, list[dict]] = json.load(f)

    oca = load_json(oca_path)
    greek = load_json(greek_path)

    oca_index = build_oca_index(oca)

    # Also build index of saints already in greek_saints.json to avoid duplication
    greek_existing: set[str] = set()
    for entry in greek:
        for saint in entry.get("saints", []):
            for key in saint_keys(saint["name"], saint.get("title")):
                greek_existing.add(key)

    # Track changes
    oca_enriched = 0          # saints in OCA that got goarch_url added
    new_greek: dict[str, list[dict]] = {}  # MM-DD → new Greek saints
    already_have_goarch = 0   # saints already had goarch_url

    # Filter out placeholder/metadata keys (e.g. _comment, _note) and non-list values
    # left by the unfilled goarch_raw.json stub.
    goarch_raw = {
        k: v for k, v in goarch_raw.items()
        if not k.startswith("_") and isinstance(v, list)
    }
    if not goarch_raw:
        print("ERROR: goarch_raw.json contains no saint data. Run import_goarch.py first.",
              file=sys.stderr)
        sys.exit(1)

    total_goarch = sum(len(v) for v in goarch_raw.values())
    print(f"GOARCH input: {total_goarch} saints across {len(goarch_raw)} days", file=sys.stderr)

    for mm_dd, goarch_saints in sorted(goarch_raw.items()):
        day_index = oca_index.get(mm_dd, {})

        for gs in goarch_saints:
            name = gs["name"]
            goarch_url = gs["goarch_url"]

            norm_keys = saint_keys(name)
            matched_saint = None
            for k in norm_keys:
                if k in day_index:
                    matched_saint = day_index[k]
                    break

            if matched_saint is not None:
                # Saint is in OCA — add goarch_url if missing
                if matched_saint.get("goarch_url"):
                    already_have_goarch += 1
                else:
                    matched_saint["goarch_url"] = goarch_url
                    oca_enriched += 1
            else:
                # Not in OCA — candidate for greek_saints.json
                # Check it's not already in greek overlay
                is_dup = any(k in greek_existing for k in norm_keys)
                if is_dup:
                    continue

                notes = None
                if args.fetch_notes:
                    notes = _fetch_goarch_notes(goarch_url)
                    if notes:
                        print(f"    {mm_dd} {name[:50]} → notes fetched", file=sys.stderr)
                    time.sleep(args.delay)

                new_entry = {
                    "name": name,
                    "title": name,
                    "feast_type": _feast_type(name),
                    "hagiography_url": None,
                    "goarch_url": goarch_url,
                    "icon_url": None,
                    "notes": notes,
                    "canonized_by": "Ecumenical Patriarchate of Constantinople",
                    "canonization_scope": "local",
                    "year_canonized": None,
                }
                new_greek.setdefault(mm_dd, []).append(new_entry)
                for k in norm_keys:
                    greek_existing.add(k)

    new_greek_count = sum(len(v) for v in new_greek.values())
    print(
        f"OCA matched: {oca_enriched} saints got goarch_url "
        f"({already_have_goarch} already had it)",
        file=sys.stderr,
    )
    print(f"New Greek saints (not in OCA): {new_greek_count}", file=sys.stderr)

    if args.dry_run:
        if new_greek:
            print("\nNew Greek saints preview:", file=sys.stderr)
            for mm_dd, saints in sorted(new_greek.items()):
                for s in saints:
                    print(f"  {mm_dd}  {s['name']}")
        return

    # Write updated oca_julian.json
    if oca_enriched > 0:
        with oca_path.open("w", encoding="utf-8") as f:
            json.dump(oca, f, ensure_ascii=False, indent=2)
        print(f"Updated {oca_path} ({oca_enriched} saints enriched with goarch_url)", file=sys.stderr)

    # Merge new Greek saints into greek_saints.json
    if new_greek:
        # Index existing greek entries by MM-DD
        greek_by_md: dict[str, dict] = {e["month_day"]: e for e in greek}
        for mm_dd, saints in new_greek.items():
            if mm_dd in greek_by_md:
                seen = {s["name"] for s in greek_by_md[mm_dd]["saints"]}
                for s in saints:
                    if s["name"] not in seen:
                        greek_by_md[mm_dd]["saints"].append(s)
                        seen.add(s["name"])
            else:
                greek_by_md[mm_dd] = {
                    "month_day": mm_dd,
                    "tradition": "greek",
                    "calendar": "revised",
                    "saints": saints,
                }
        greek_out = [greek_by_md[md] for md in sorted(greek_by_md)]
        with greek_path.open("w", encoding="utf-8") as f:
            json.dump(greek_out, f, ensure_ascii=False, indent=2)
        total_greek = sum(len(e["saints"]) for e in greek_out)
        print(
            f"Updated {greek_path} (+{new_greek_count} new saints, "
            f"{total_greek} total)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
