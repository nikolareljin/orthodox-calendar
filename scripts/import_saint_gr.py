#!/usr/bin/env python3
"""
Scrape saint.gr (Ορθόδοξος Συναξαριστής) for all Greek Orthodox saints.

saint.gr is the comprehensive Greek Orthodox Synaxarion, keyed by Gregorian/
Revised Julian dates (same MM-DD as the New Calendar used by Greek Orthodox,
Bulgarian, Romanian churches).

URL patterns:
    Daily calendar: https://www.saint.gr/MM/DD/index.aspx
    Saint page:     https://www.saint.gr/ID/saint.aspx

Output (saint_gr_raw.json):
    { "MM-DD": [{"id": 3200, "name_gr": "Όσιος Παΐσιος...", "url": "..."}] }

Usage:
    python3 scripts/import_saint_gr.py [--out scripts/saint_gr_raw.json]
    python3 scripts/import_saint_gr.py --dry-run          # January only
    python3 scripts/import_saint_gr.py --start 07-01 --end 07-31
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE_URL = "https://www.saint.gr"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "el,en-US;q=0.7,en;q=0.3",
}

# Feast-day saints are always preceded by a div with class "w3-quarter w3-left-align w3-padding-4".
# Pinned/featured saints use "w3-col w3-margin-top" or "w3-bar-item" containers — excluded.
# Each w3-quarter block contains: <a href="/ID/saint.aspx"> ... <img alt="Name" title="Name"> ... </a>
_QUARTER_START_RE = re.compile(r'<div[^>]+class=["\'][^"\']*w3-quarter[^"\']*["\']')
_HREF_RE = re.compile(r'href=["\'](?P<path>/\d+/saint\.aspx)["\']')
_IMG_NAME_RE = re.compile(r'<img\s[^>]+(?:alt|title)\s*=\s*["\'](?P<name>[^"\']{2,})["\']')
_ID_RE = re.compile(r'^/(\d+)/saint\.aspx$')
_WHITESPACE_RE = re.compile(r'\s+')
_NBSP = re.compile(r'&nbsp;|&#160;')


def _clean_name(raw: str) -> str:
    s = _NBSP.sub(' ', raw)
    s = re.sub(r'<[^>]+>', '', s)
    s = _WHITESPACE_RE.sub(' ', s).strip()
    # Strip trailing year ranges like "(1924 - 1994)"
    s = re.sub(r'\s*\(\d{4}\s*[-–]\s*\d{4}\)\s*$', '', s).strip()
    return s


def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = 'utf-8'
        ct = resp.headers.get('Content-Type', '')
        m = re.search(r'charset=([^\s;]+)', ct)
        if m:
            charset = m.group(1)
        try:
            return raw.decode(charset, errors='replace')
        except LookupError:
            return raw.decode('utf-8', errors='replace')


def fetch_day(month: int, day: int) -> list[dict]:
    """Fetch all saints listed for a given Gregorian MM/DD from saint.gr."""
    url = f"{BASE_URL}/{month:02d}/{day:02d}/index.aspx"
    try:
        html = _fetch(url)
    except Exception as exc:
        print(f"  WARN {month:02d}-{day:02d}: {exc}", file=sys.stderr)
        return []

    seen_ids: set[int] = set()
    saints: list[dict] = []

    # Only collect saints from w3-quarter blocks (feast-day grid).
    # Each block: <div class="w3-quarter..."><a href="/ID/saint.aspx"><img title="Name"/></a></div>
    for qs in _QUARTER_START_RE.finditer(html):
        window = html[qs.start(): qs.start() + 700]
        hm = _HREF_RE.search(window)
        if not hm:
            continue
        nm = _IMG_NAME_RE.search(window)
        if not nm:
            continue

        path = hm.group('path')
        id_m = _ID_RE.match(path)
        if not id_m:
            continue
        saint_id = int(id_m.group(1))
        if saint_id in seen_ids:
            continue
        seen_ids.add(saint_id)

        name_gr = _clean_name(nm.group('name'))
        if not name_gr or len(name_gr) < 2:
            continue

        saints.append({
            "id": saint_id,
            "name_gr": name_gr,
            "url": f"{BASE_URL}{path}",
        })

    return saints


def iter_days(start_mm_dd: str = "01-01", end_mm_dd: str = "12-31"):
    """Yield (month, day) tuples for a leap year bounded by start/end."""
    # Use 2024 (leap year) to include Feb 29
    anchor = date(2024, 1, 1)
    end_date = date(2024, int(end_mm_dd[:2]), int(end_mm_dd[3:]))
    cur = date(2024, int(start_mm_dd[:2]), int(start_mm_dd[3:]))
    while cur <= end_date:
        yield cur.month, cur.day
        cur += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape saint.gr Greek Orthodox calendar")
    parser.add_argument("--out", default="scripts/saint_gr_raw.json",
                        help="Output JSON path (default: scripts/saint_gr_raw.json)")
    parser.add_argument("--delay", type=float, default=0.4,
                        help="Seconds between requests (default 0.4)")
    parser.add_argument("--start", default="01-01", help="Start MM-DD (default 01-01)")
    parser.add_argument("--end", default="12-31", help="End MM-DD (default 12-31)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape January only, print summary, do not write")
    args = parser.parse_args()

    if args.dry_run:
        args.start = "01-01"
        args.end = "01-31"

    out_path = Path(args.out)
    result: dict[str, list[dict]] = {}

    # Merge existing output if present (allows resuming interrupted runs)
    if out_path.exists():
        with out_path.open(encoding='utf-8') as f:
            result = json.load(f)
        print(f"Resuming from {out_path} ({len(result)} days already scraped)", file=sys.stderr)

    days = list(iter_days(args.start, args.end))
    print(f"Scraping {len(days)} days from saint.gr ({args.start}–{args.end})...", file=sys.stderr)

    for month, day in days:
        mm_dd = f"{month:02d}-{day:02d}"
        if mm_dd in result:
            continue  # already done (resume mode)

        saints = fetch_day(month, day)
        result[mm_dd] = saints
        count = len(saints)
        if count:
            print(f"  {mm_dd}: {count} saints", file=sys.stderr)

        if not args.dry_run:
            # Write checkpoint after every day (safe to interrupt)
            with out_path.open('w', encoding='utf-8') as f:
                json.dump(dict(sorted(result.items())), f, ensure_ascii=False, indent=2)

        time.sleep(args.delay)

    total = sum(len(v) for v in result.values())
    print(f"\nTotal: {total} saints across {len(result)} days", file=sys.stderr)

    if args.dry_run:
        for mm_dd, saints in sorted(result.items()):
            for s in saints:
                print(f"  {mm_dd}  id={s['id']}  {s['name_gr'][:60]}")
        return

    with out_path.open('w', encoding='utf-8') as f:
        json.dump(dict(sorted(result.items())), f, ensure_ascii=False, indent=2)
    print(f"Wrote → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
