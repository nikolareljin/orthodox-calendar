#!/usr/bin/env python3
"""
Enrich oca_julian.json with full hagiography text from orthocal.info.

The orthocal.info API returns hagiographic stories in the `stories` field.
This script fetches each day's stories and updates the `notes` field for
matching saints in oca_julian.json WITHOUT touching hagiography_url or
any other field (preserving all OCA URLs from the original import).

Matching: stories are matched to saints by title normalization, using the
same algorithm as services/saints.py (_normalize_saint_text).

Usage:
    python3 scripts/enrich_oca_notes.py [--dry-run] [--delay 0.3] [--start 01-01] [--end 12-31]

    # Only update empty notes (default)
    python3 scripts/enrich_oca_notes.py

    # Overwrite ALL notes with full text from orthocal.info
    python3 scripts/enrich_oca_notes.py --force

    # One specific date
    python3 scripts/enrich_oca_notes.py --start 01-14 --end 01-14
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _name_utils import normalize  # noqa: E402

ORTHOCAL_API = "https://orthocal.info/api/julian/{year}/{month}/{day}/"
OCA_PATH = Path("backend/app/data/oca_julian.json")

# orthocal.info Julian API takes CIVIL Gregorian dates and returns the saints
# observed on that civil date by Julian-calendar churches.
# Our oca_julian.json is keyed by JULIAN ECCLESIASTICAL dates.
# Conversion uses JDN arithmetic (works for any century, not just 1900–2099).


def julian_mm_dd_to_civil(julian_month: int, julian_day: int, year: int = 2024) -> tuple[int, int, int]:
    """Convert a Julian ecclesiastical MM-DD to its civil (Gregorian) year/month/day via JDN."""
    # year=2024 (leap) ensures Feb 29 Julian is always valid as input
    a = (14 - julian_month) // 12
    y = year + 4800 - a
    m = julian_month + 12 * a - 3
    jdn = julian_day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    a4 = jdn + 32044
    b4 = (4 * a4 + 3) // 146097
    c4 = a4 - (146097 * b4) // 4
    d4 = (4 * c4 + 3) // 1461
    e4 = c4 - (1461 * d4) // 4
    m4 = (5 * e4 + 2) // 153
    gday = e4 - (153 * m4 + 2) // 5 + 1
    gmonth = m4 + 3 - 12 * (m4 // 10)
    gyear = 100 * b4 + d4 - 4800 + m4 // 10
    return gyear, gmonth, gday

_STRIP_DATE_RE = re.compile(r"\s*\(?\d{3,4}\)?\s*$")  # strip trailing " (379)" year


def _story_norm(title: str) -> str:
    """Normalize a story title for matching against saint names."""
    title = _STRIP_DATE_RE.sub("", title.strip())
    return normalize(title)


def fetch_stories(julian_month: int, julian_day: int) -> list[dict]:
    """Fetch orthocal.info stories for a Julian ecclesiastical MM-DD.

    Converts the Julian date to the civil date (+13 days) before calling the API,
    because orthocal.info's Julian endpoint takes civil (Gregorian) dates and
    returns the saints observed by Julian-calendar churches on that civil date.
    """
    civil_year, civil_month, civil_day = julian_mm_dd_to_civil(julian_month, julian_day)
    url = ORTHOCAL_API.format(year=civil_year, month=civil_month, day=civil_day)
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "orthodox-calendar-importer/1.0"}),
            timeout=15,
        ) as resp:
            data = json.loads(resp.read())
        return [s for s in data.get("stories", []) if isinstance(s, dict) and s.get("story")]
    except Exception as exc:
        print(f"  WARN {julian_month:02d}-{julian_day:02d}: {exc}", file=sys.stderr)
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich OCA notes from orthocal.info stories")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches, write nothing")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing non-empty notes (default: only fill empty)")
    parser.add_argument("--delay", type=float, default=0.35,
                        help="Seconds between API requests (default 0.35)")
    parser.add_argument("--start", default="01-01",
                        help="Start MM-DD (default 01-01)")
    parser.add_argument("--end", default="12-31",
                        help="End MM-DD (default 12-31)")
    parser.add_argument("--oca", default=str(OCA_PATH),
                        help="Path to oca_julian.json")
    args = parser.parse_args()

    oca_path = Path(args.oca)
    with oca_path.open(encoding="utf-8") as f:
        oca: list[dict] = json.load(f)

    updated = 0
    skipped_no_match = 0

    entries_in_range = [
        e for e in oca
        if args.start <= e["month_day"] <= args.end
    ]
    total = len(entries_in_range)
    print(f"Processing {total} days ({args.start}–{args.end})...", file=sys.stderr)

    for i, entry in enumerate(entries_in_range):
        mm_dd = entry["month_day"]
        month, day = int(mm_dd[:2]), int(mm_dd[3:])

        stories = fetch_stories(month, day)
        if not stories:
            time.sleep(args.delay)
            continue

        # Build story lookup: {norm_key: full_text}
        story_map: dict[str, str] = {}
        for s in stories:
            k = _story_norm(s["title"])
            if k:
                story_map[k] = s["story"].strip()

        for saint in entry.get("saints", []):
            # Try to match by title or name
            match_text = None
            for candidate in [saint.get("title", ""), saint.get("name", "")]:
                k = normalize(_STRIP_DATE_RE.sub("", candidate))
                if k in story_map:
                    match_text = story_map[k]
                    break
                # Partial match: story key is substring of saint key or vice versa
                for sk, sv in story_map.items():
                    if len(sk) >= 5 and (sk in k or k in sk):
                        match_text = sv
                        break
                if match_text:
                    break

            if match_text:
                current_notes = saint.get("notes") or ""
                should_update = args.force or len(current_notes) < len(match_text)
                if should_update:
                    if not args.dry_run:
                        saint["notes"] = match_text
                    updated += 1
                    if args.dry_run or (i < 5 and updated <= 10):
                        name = (saint.get("title") or saint.get("name", ""))[:50]
                        print(f"  {mm_dd} {name}: {len(match_text)} chars", file=sys.stderr)
            else:
                skipped_no_match += 1

        time.sleep(args.delay)

    print(
        f"\nUpdated: {updated} saints   No match: {skipped_no_match}",
        file=sys.stderr,
    )

    if not args.dry_run and updated > 0:
        with oca_path.open("w", encoding="utf-8") as f:
            json.dump(oca, f, ensure_ascii=False, indent=2)
        print(f"Wrote → {oca_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
