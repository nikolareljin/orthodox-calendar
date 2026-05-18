#!/usr/bin/env python3
"""
Import Coptic Orthodox saints from the coptic.io GraphQL API.

The coptic.io API returns Synaxarium entries (saints, commemorations) and
liturgical Celebrations (major feasts, fasts) keyed by Gregorian date.
We store data as Gregorian month_day keys so the lookup works directly
without calendar conversion.

Usage:
    python3 scripts/import_coptic.py --out backend/app/data/traditions/coptic_saints.json
    python3 scripts/import_coptic.py --year 2024 --delay 0.5 --out /path/to/output.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

GRAPHQL_URL = "https://api.coptic.io/graphql"

# One GraphQL query per date — returns synaxarium entries, celebrations, and
# the Coptic calendar date (used as a human-readable note).
_QUERY = """
query DayData($date: String) {
  readings(date: $date) {
    fullDate {
      day
      month
      monthString
    }
    Synaxarium {
      name
      url
    }
    celebrations {
      id
      name
      type
    }
  }
}
"""


_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(GRAPHQL_URL, data=payload, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _feast_type_from_name(name: str) -> str:
    """Infer feast_type from the synaxarium entry name."""
    lower = name.lower()
    if re.search(r"\bdeparture\b", lower):
        return "Martyr" if re.search(r"\bmartyr\b", lower) else "Saint"
    if re.search(r"\bconsecration\b|\bdedication\b", lower):
        return "Feast"
    if re.search(r"\bpassion\b|\bmartyr\b|\bwitness\b", lower):
        return "Martyr"
    if re.search(r"\bcommemoration\b|\banniversary\b", lower):
        return "Feast"
    if re.search(r"\bpope\b|\bpatriarch\b|\bbishop\b|\barchbishop\b", lower):
        return "Hierarch"
    if re.search(r"\bmonk\b|\bhermit\b|\bascet\b|\bvenerable\b", lower):
        return "Venerable"
    if re.search(r"\bapostle\b|\bevangelist\b", lower):
        return "Apostle"
    return "Coptic Saint"


def _short_name(full_name: str) -> str:
    """Extract a short personal name from a synaxarium entry title."""
    name = full_name.rstrip(".")
    # Strip leading "The " before the verb
    name = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
    # Strip event verb + "of [the] [church of] [the]"
    name = re.sub(
        r"^(?:departure|repose|commemoration|consecration|dedication|feast|synaxis|"
        r"translation|uncovering|discovery)\s+of\s+(?:the\s+church\s+of\s+)?(?:the\s+)?",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    return name[:1].upper() + name[1:] if name else full_name


_CELEBRATION_FEAST_TYPES = {
    "feast": "Great Feast",
    "lordlyFeast": "Great Feast",
    "fast": "Fast",
    "season": "Season",
}


def fetch_day(gregorian_date: date) -> dict:
    date_str = gregorian_date.isoformat()
    result = _graphql(_QUERY, {"date": date_str})
    data = result.get("data", {})
    errors = result.get("errors")
    if errors:
        raise RuntimeError(f"GraphQL errors for {date_str}: {errors}")
    return data.get("readings", {})


def build_entry(gregorian_date: date, readings: dict) -> dict | None:
    """Convert a readings response into a CalendarEntry dict."""
    synaxarium = readings.get("Synaxarium") or []
    celebrations = readings.get("celebrations") or []
    full_date = readings.get("fullDate") or {}

    saints = []

    # Synaxarium entries (specific saints/commemorations for the day)
    for entry in synaxarium:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        saints.append({
            "name": _short_name(name),
            "title": name,
            "feast_type": _feast_type_from_name(name),
            "hagiography_url": entry.get("url") or None,
            "notes": None,
            "canonized_by": None,
            "canonization_scope": None,
            "year_canonized": None,
        })

    # Major liturgical celebrations (feasts, fasts) — only include feasts/lordlyFeasts
    for cel in celebrations:
        cel_type = cel.get("type", "")
        if cel_type in ("fast", "season"):
            continue
        cel_name = (cel.get("name") or "").strip()
        if not cel_name:
            continue
        # Avoid duplicates if the synaxarium already listed this by name
        if any(s["title"] == cel_name for s in saints):
            continue
        saints.append({
            "name": cel_name,
            "title": cel_name,
            "feast_type": _CELEBRATION_FEAST_TYPES.get(cel_type, "Great Feast"),
            "hagiography_url": None,
            "notes": None,
            "canonized_by": None,
            "canonization_scope": None,
            "year_canonized": None,
        })

    if not saints:
        return None

    month_day = gregorian_date.strftime("%m-%d")
    coptic_note = None
    if full_date.get("monthString") and full_date.get("day"):
        coptic_note = f"Coptic {full_date['monthString']} {full_date['day']}"

    return {
        "month_day": month_day,
        "tradition": "coptic",
        "calendar": "gregorian",
        "saints": saints,
        "notes": coptic_note,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Coptic saints from coptic.io GraphQL API")
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="Gregorian year to iterate (use a leap year to include Feb 29; default: 2024)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Delay between requests in seconds (default: 0.4)",
    )
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/coptic_saints.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    d = date(args.year, 1, 1)
    end = date(args.year + 1, 1, 1)
    entries = []
    errors = 0

    print(f"Fetching Coptic calendar for Gregorian year {args.year} from coptic.io...", file=sys.stderr)

    while d < end:
        try:
            readings = fetch_day(d)
            entry = build_entry(d, readings)
            if entry:
                entries.append(entry)
                saint_count = len(entry["saints"])
                coptic = entry.get("notes", "")
                print(f"  {d.isoformat()} ({coptic}): {saint_count} saints/feasts", file=sys.stderr)
            else:
                print(f"  {d.isoformat()}: no saints", file=sys.stderr)
        except Exception as exc:
            print(f"  {d.isoformat()}: ERROR — {exc}", file=sys.stderr)
            errors += 1
        finally:
            time.sleep(args.delay)
        d += timedelta(days=1)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(
        f"\nWrote {len(entries)} entries ({sum(len(e['saints']) for e in entries)} total saints/feasts) "
        f"to {out_path}",
        file=sys.stderr,
    )
    if errors:
        print(f"Errors: {errors} days failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
