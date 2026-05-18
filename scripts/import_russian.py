#!/usr/bin/env python3
"""
Import Russian Orthodox saints from orthocal.info (Julian calendar).

This script fetches the full Julian calendar from orthocal.info — the same
source as oca_julian.json — but writes the data under the "russian" tradition
key. The overlay is then filtered for Russia-specific commemorations using a
keyword list (New Martyrs, Russian place names, ROC canonization markers).

For saints that are not in the list of Russia-specific keywords, they are
skipped (they already appear in oca_julian.json / the base dataset). This
produces a lightweight overlay of ~200–400 Russian-specific saints rather than
a full 2,970-entry duplication.

Usage:
    python3 scripts/import_russian.py --out backend/app/data/traditions/russian_saints.json
    python3 scripts/import_russian.py --year 2024 --delay 0.3 --full
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE_URL = "https://orthocal.info/api"

# Patterns that identify Russia-specific saints not present in the OCA base
# or that deserve Russian-tradition tagging for canonization context.
_RUSSIAN_PATTERNS = [
    # New Martyrs and Confessors
    r"\bnew martyr\b",
    r"\bconfessor of russia\b",
    r"\bconfessor.*russia\b",
    r"\bnew martyr.*russia\b",
    r"\brussia\b",
    r"\brussian\b",
    # WWII / Communist persecution martyrs
    r"\b1937\b|\b1938\b|\b1941\b|\b1942\b|\b1943\b|\b1944\b",
    # Russian cities and monasteries
    r"\boptina\b",
    r"\bsarov\b",
    r"\bradonezh\b",
    r"\bkiev\b",
    r"\bnovgorod\b",
    r"\bpskov\b",
    r"\bsolovki\b|\bsolovetsk\b",
    r"\bvalaam\b",
    r"\bpechory\b|\bpechersk\b",
    # Notable Russian saints by name fragment
    r"\bseraphim.*sarov\b|\bsarov.*seraphim\b",
    r"\bsergius.*radonezh\b",
    r"\btikhon.*patriarch\b|\bpatriarch.*tikhon\b",
    r"\belizabeth feodorovna\b|\bgrand duchess\b",
    r"\bmatrona\b",
    r"\bjohn.*kronstadt\b|\bkronstadt.*john\b",
    r"\bxenia.*petersburg\b",
    r"\bherman.*alaska\b|\balaska.*herman\b",
    # Canonized by ROC explicit
    r"\bcanonized.*russian\b",
    r"\bpatriarch of moscow\b",
    r"\bmetropolitan.*moscow\b",
    r"\bmoscow\b",
    # Monastic foundations
    r"\bhierarch.*russia\b",
]

_RUSSIAN_RE = re.compile("|".join(_RUSSIAN_PATTERNS), re.IGNORECASE)

FEAST_TYPE_NAMES = {
    1: "Great Feast",
    2: "Vigil",
    3: "Polyeleos",
    4: "Doxology",
    5: "Minor Feast",
    6: "Memorial",
    7: "Hierarch",
    8: "Martyr",
    9: "Venerable",
    10: "Righteous",
    11: "Apostle",
    12: "Prophet",
    13: "Equal-to-Apostles",
}


def fetch_day(year: int, month: int, day: int) -> dict:
    url = f"{BASE_URL}/julian/{year}/{month}/{day}/"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def _is_russian(name: str) -> bool:
    return bool(_RUSSIAN_RE.search(name))


def parse_entry(data: dict, month_day: str, full_mode: bool) -> dict | None:
    """Build a CalendarEntry dict for the Russian tradition overlay."""
    saints_raw = data.get("saints") or []
    stories_by_title = {s["title"]: s for s in data.get("stories", []) if s.get("title")}

    saints = []
    for saint_name in saints_raw:
        if not full_mode and not _is_russian(saint_name):
            continue
        story = stories_by_title.get(saint_name, {})
        notes = (story.get("story", "") or "")[:500].strip()
        source_url = story.get("source_url") or None
        saints.append({
            "name": saint_name.split(",")[0].strip(),
            "title": saint_name,
            "feast_type": "New Martyr" if re.search(r"\bnew martyr\b", saint_name, re.IGNORECASE) else "Saint",
            "hagiography_url": source_url,
            "notes": notes or None,
            "canonized_by": "Russian Orthodox Church",
            "canonization_scope": "local",
            "year_canonized": None,
        })

    if not saints:
        return None

    return {
        "month_day": month_day,
        "tradition": "russian",
        "calendar": "julian",
        "saints": saints,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Russian Orthodox saints from orthocal.info")
    parser.add_argument("--year", type=int, default=2024, help="Year to fetch (default: 2024)")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between requests (default: 0.3s)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include ALL Julian saints (not just Russia-specific); produces a full overlay",
    )
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/russian_saints.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    d = date(args.year, 1, 1)
    end = date(args.year + 1, 1, 1)
    entries = []
    seen_julian: set[str] = set()
    errors = 0

    mode = "full" if args.full else "Russia-specific overlay"
    print(f"Fetching Russian Orthodox calendar ({mode}) for {args.year}...", file=sys.stderr)

    while d < end:
        # Julian calendar: iterate by Julian dates. Use the same year but
        # request via the Julian API endpoint. The API handles Julian leap years.
        month_day = d.strftime("%m-%d")
        if month_day not in seen_julian:
            seen_julian.add(month_day)
            try:
                data = fetch_day(d.year, d.month, d.day)
                entry = parse_entry(data, month_day, args.full)
                if entry:
                    entries.append(entry)
                    print(f"  {month_day}: {len(entry['saints'])} saints", file=sys.stderr)
                else:
                    print(f"  {month_day}: no Russian-specific saints", file=sys.stderr)
            except Exception as exc:
                print(f"  {month_day}: ERROR — {exc}", file=sys.stderr)
                errors += 1
            finally:
                time.sleep(args.delay)
        d += timedelta(days=1)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    total_saints = sum(len(e["saints"]) for e in entries)
    print(
        f"\nWrote {len(entries)} entries ({total_saints} saints) to {out_path}",
        file=sys.stderr,
    )
    if errors:
        print(f"Errors: {errors} days failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
