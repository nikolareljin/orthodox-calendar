#!/usr/bin/env python3
"""
Import Byzantine saints from orthocal.info API.

Usage:
    python3 scripts/import_orthocal.py --calendar julian --data-key oca --out backend/app/data/oca_julian.json
    python3 scripts/import_orthocal.py --calendar gregorian --data-key oca --out backend/app/data/oca_revised.json

The orthocal.info API supports:
    GET https://orthocal.info/api/{julian|gregorian}/{year}/{month}/{day}/

Response structure:
    {
      "year": int, "month": int, "day": int,
      "commemorations": [
        {
          "title": "Full title of feast/saint",
          "subtitle": "Short name",
          "feast_type": int,  # maps to feast type strings
          "source_url": "https://..."
        }
      ],
      "fast_level": int,
      "fast_exception": int,
      "feasts": [{"title": str}],
      "stories": [{"title": str, "story": str, "source_url": str}]
    }

    Note: The exact response shape may vary. The key field is "commemorations" or "saints".
    Use a try/except and log any parsing failures.
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path


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

BASE_URL = "https://orthocal.info/api"


def fetch_day(calendar: str, year: int, month: int, day: int) -> dict:
    url = f"{BASE_URL}/{calendar}/{year}/{month}/{day}/"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def parse_saints(data: dict, tradition: str, calendar: str, month_day: str) -> dict | None:
    """Parse orthocal.info response into a CalendarEntry dict."""
    saints = []

    # orthocal.info uses "commemorations"; some responses use "saints" instead
    commemorations = data.get("commemorations") or data.get("saints", [])
    stories_by_title = {s["title"]: s for s in data.get("stories", []) if s.get("title")}

    for comm in commemorations:
        title = comm.get("title", "")
        feast_type_int = comm.get("feast_type", 0)
        feast_type = FEAST_TYPE_NAMES.get(feast_type_int, "Saint")
        source_url = comm.get("source_url") or comm.get("src", "")

        # Try to get hagiography from stories
        story = stories_by_title.get(title, {})
        notes = story.get("story", "")[:500] if story else ""  # truncate

        saints.append({
            "name": comm.get("subtitle") or title.split(",")[0],
            "title": title,
            "feast_type": feast_type,
            "hagiography_url": source_url or None,
            "notes": notes or None,
        })

    if not saints:
        return None

    return {
        "month_day": month_day,
        "tradition": tradition,
        "calendar": calendar,
        "saints": saints,
    }


def main():
    parser = argparse.ArgumentParser(description="Import saints from orthocal.info")
    parser.add_argument("--calendar", choices=["julian", "gregorian"], default="julian")
    parser.add_argument("--data-key", default="oca", dest="data_key",
                        help="Tradition/data key written into each output entry (default: oca)")
    parser.add_argument("--out", default=None, help="Output JSON file path")
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="Year to fetch (use a leap year to include Feb 29)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between requests in seconds (default: 0.3)",
    )
    args = parser.parse_args()

    out_path = args.out or f"backend/app/data/oca_{args.calendar}.json"

    d = date(args.year, 1, 1)
    end = date(args.year + 1, 1, 1)

    entries = []
    seen_month_days: set[str] = set()

    print(f"Fetching {args.calendar} calendar for year {args.year}...", file=sys.stderr)

    while d < end:
        month_day = d.strftime("%m-%d")

        if month_day not in seen_month_days:
            seen_month_days.add(month_day)
            try:
                data = fetch_day(args.calendar, d.year, d.month, d.day)
                entry = parse_saints(data, args.data_key, args.calendar, month_day)
                if entry:
                    entries.append(entry)
                    print(f"  {month_day}: {len(entry['saints'])} saints", file=sys.stderr)
                time.sleep(args.delay)
            except Exception as exc:
                print(f"  {month_day}: ERROR - {exc}", file=sys.stderr)

        d += timedelta(days=1)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(entries)} entries to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
