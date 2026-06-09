#!/usr/bin/env python3
"""
Build a GOARCH saints hagiography cache by fetching archived chapel saint pages
from the Wayback Machine (web.archive.org), then enrich greek_saints.json with
GOARCH URLs and hagiography text.

Two phases:
  Phase 1 — Crawl: fetch each known contentid from Wayback, extract name/text/date,
            save to goarch_hagio_cache.json.
  Phase 2 — Enrich: match cache entries against greek_saints.json by normalized name
            and fill in hagiography_url + notes.

Usage:
    # Full run (crawl + enrich)
    python3 scripts/enrich_goarch_from_wayback.py \\
        --cache scripts/goarch_hagio_cache.json \\
        --greek backend/app/data/traditions/greek_saints.json \\
        --delay 0.5

    # Crawl only (build cache without modifying greek_saints.json)
    python3 scripts/enrich_goarch_from_wayback.py --crawl-only

    # Enrich only (use existing cache)
    python3 scripts/enrich_goarch_from_wayback.py --enrich-only

    # Dry run (show matches, write nothing)
    python3 scripts/enrich_goarch_from_wayback.py --dry-run
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WAYBACK_BASE = "https://web.archive.org/web"
GOARCH_SAINT_URL = "https://www.goarch.org/chapel/saints?contentid={contentid}"
# Direct archived URL using a known CDX timestamp — avoids Wayback redirecting to live GOARCH
WAYBACK_URL = f"{WAYBACK_BASE}/{{timestamp}}/{GOARCH_SAINT_URL}"

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)",
    "Accept": "text/html",
}

# Known contentids from Wayback CDX API (as of 2025).
# Run: curl -s "https://web.archive.org/cdx/search/cdx?url=www.goarch.org/chapel/saints%3Fcontentid%3D*
#        &output=json&limit=5000&fl=original&filter=statuscode:200&collapse=original"
# and extract integer contentids.  This list can be expanded over time.
_DEFAULT_CONTENTIDS_FILE = Path(__file__).parent / "goarch_contentids.txt"

# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.DOTALL | re.IGNORECASE)
_DATE_RE = re.compile(r'<h1[^>]*class="date"[^>]*>(.*?)</h1>', re.DOTALL | re.IGNORECASE)
_READING_RE = re.compile(
    r'<h3[^>]*>\s*Reading\s*</h3>\s*<p>(.*?)</p>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _strip(html: str) -> str:
    return _TAG_RE.sub(" ", html)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_month_day(date_str: str) -> str | None:
    """Parse 'April 1', 'September 14' → 'MM-DD'."""
    m = re.match(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
        date_str.strip(),
        re.IGNORECASE,
    )
    if m:
        month = _MONTH_MAP[m.group(1).lower()]
        day = int(m.group(2))
        return f"{month:02d}-{day:02d}"
    # "1 April" form
    m = re.match(
        r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)",
        date_str.strip(),
        re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP[m.group(2).lower()]
        return f"{month:02d}-{day:02d}"
    return None


def fetch_saint(contentid: int, timestamp: str = "2025") -> dict | None:
    """Fetch a GOARCH chapel saint page from Wayback Machine and extract metadata."""
    url = WAYBACK_URL.format(timestamp=timestamp, contentid=contentid)
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARN contentid={contentid}: {exc}", file=sys.stderr)
        return None

    # Extract saint name from <title>
    title_m = _TITLE_RE.search(html)
    if not title_m:
        return None
    title_raw = html_module.unescape(_clean(_strip(title_m.group(1))))
    # Strip "- Greek Orthodox Archdiocese of America" suffix and similar
    name = re.sub(r"\s*-\s*(?:Greek Orthodox|GOARCH).*$", "", title_raw, flags=re.IGNORECASE).strip()
    if not name or "wayback" in name.lower() or len(name) < 3:
        return None

    # Extract date
    date_m = _DATE_RE.search(html)
    month_day = _parse_month_day(_clean(_strip(date_m.group(1)))) if date_m else None

    # Extract hagiography text (Reading section)
    reading_m = _READING_RE.search(html)
    extended_notes = None
    if reading_m:
        text = _clean(_strip(reading_m.group(1)))
        if len(text) > 40:
            extended_notes = text

    return {
        "contentid": contentid,
        "name": name,
        "month_day": month_day,
        "goarch_url": GOARCH_SAINT_URL.format(contentid=contentid),
        "extended_notes": extended_notes,
    }


# ---------------------------------------------------------------------------
# Name normalization (mirrors backend/_name_utils.py)
# ---------------------------------------------------------------------------

_NORM_STRIP = re.compile(
    r"\bthe\b|\bblessed\b|\bholy\b|\bsaint\b|\bst\.\b|\bvenerable\b|\brighteous\b"
    r"|\bmartyr\b|\bapostle\b|\bprophet\b|\bhieromartyr\b|\bhierarch\b"
    r"|\bconfessor\b|\bdeacon\b|\bbishop\b|\barchbishop\b|\bpatriarch\b"
    r"|\bmetropolitan\b|\bpresbyter\b|\bmonk\b|\bnun\b|\babbess\b|\babbot\b",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    name = name.lower()
    name = _NORM_STRIP.sub("", name)
    name = re.sub(r"[^a-z]", "", name)
    return name


def _saint_key(name: str, title: str | None = None) -> str:
    return _normalize(title or name)


# ---------------------------------------------------------------------------
# Phase 1: Crawl
# ---------------------------------------------------------------------------

def crawl(contentids: list[int], cache_path: Path, delay: float) -> dict:
    """Fetch all contentids and save cache. Returns {contentid: entry}."""
    existing: dict = {}
    if cache_path.exists():
        existing = json.loads(cache_path.read_text())
        print(f"Loaded {len(existing)} existing cache entries from {cache_path}", file=sys.stderr)

    # Load CDX timestamps if available — direct timestamp URLs never redirect to live GOARCH.
    cdx_file = Path(__file__).parent.parent.parent / "tmp" / "cdx_timestamps.json"
    _cdx_file_search = [
        Path("/tmp/cdx_timestamps.json"),
        Path(__file__).parent / "goarch_cdx_timestamps.json",
    ]
    cdx_ts: dict[str, str] = {}
    for f in _cdx_file_search:
        if f.exists():
            raw = json.loads(f.read_text())
            cdx_ts = {cid: v["timestamp"] for cid, v in raw.items()}
            print(f"Loaded {len(cdx_ts)} CDX timestamps from {f}", file=sys.stderr)
            break

    to_fetch = [cid for cid in contentids if str(cid) not in existing]
    print(f"Fetching {len(to_fetch)} new contentids...", file=sys.stderr)

    for i, cid in enumerate(to_fetch, 1):
        ts = cdx_ts.get(str(cid), "2025")
        result = fetch_saint(cid, timestamp=ts)
        if result:
            existing[str(cid)] = result
            print(f"  [{i}/{len(to_fetch)}] {cid}: {result['name'][:60]}", file=sys.stderr)
        else:
            existing[str(cid)] = None  # mark as not found so we skip next time
            print(f"  [{i}/{len(to_fetch)}] {cid}: (not found)", file=sys.stderr)

        if i % 20 == 0:  # checkpoint every 20 entries
            cache_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

        time.sleep(delay)

    cache_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    valid = {k: v for k, v in existing.items() if v}
    print(f"Cache: {len(valid)} valid entries → {cache_path}", file=sys.stderr)
    return existing


# ---------------------------------------------------------------------------
# Phase 2: Enrich
# ---------------------------------------------------------------------------

def enrich(cache: dict, greek_path: Path, dry_run: bool = False) -> None:
    """Match cache entries against greek_saints.json and fill in GOARCH data."""
    greek = json.loads(greek_path.read_text())

    # Build normalized name index from cache
    # {norm_key: entry}
    cache_by_key: dict[str, dict] = {}
    # Also index by (month_day, norm_key) for precision
    cache_by_md_key: dict[tuple, dict] = {}
    for entry in cache.values():
        if not entry:
            continue
        key = _normalize(entry["name"])
        if key:
            cache_by_key[key] = entry
        if entry.get("month_day") and key:
            cache_by_md_key[(entry["month_day"], key)] = entry

    matched = 0
    total_needing_url = 0

    for day_entry in greek:
        md = day_entry["month_day"]
        for saint in day_entry["saints"]:
            if saint.get("goarch_url"):
                continue  # already has GOARCH URL
            total_needing_url += 1

            name = saint.get("title") or saint.get("name", "")
            key = _normalize(name)
            if not key:
                continue

            # Try day+name match first (most precise)
            hit = cache_by_md_key.get((md, key)) or cache_by_key.get(key)
            if hit:
                if dry_run:
                    print(f"  MATCH {md} '{name[:50]}' → {hit['goarch_url']}")
                else:
                    saint["goarch_url"] = hit["goarch_url"]
                    saint["hagiography_url"] = hit["goarch_url"]
                    if hit.get("extended_notes"):
                        if not saint.get("notes"):
                            saint["notes"] = hit["extended_notes"][:160]
                        if not saint.get("extended_notes"):
                            saint["extended_notes"] = hit["extended_notes"]
                matched += 1

    print(f"Matched {matched}/{total_needing_url} saints with GOARCH data", file=sys.stderr)

    if not dry_run:
        greek_path.write_text(json.dumps(greek, ensure_ascii=False, indent=2))
        print(f"Wrote → {greek_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich Greek saints with GOARCH hagiography via Wayback Machine")
    parser.add_argument("--cache", default="scripts/goarch_hagio_cache.json", help="Cache file path")
    parser.add_argument("--contentids", default=None, help="File with contentids (one per line)")
    parser.add_argument("--greek", default="backend/app/data/traditions/greek_saints.json", help="Greek saints JSON")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between Wayback requests")
    parser.add_argument("--crawl-only", action="store_true", help="Only fetch from Wayback, don't enrich")
    parser.add_argument("--enrich-only", action="store_true", help="Use existing cache only, don't crawl")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without writing")
    args = parser.parse_args()

    cache_path = Path(args.cache)
    greek_path = Path(args.greek)

    if not args.enrich_only:
        # Load contentids
        cids_file = Path(args.contentids) if args.contentids else _DEFAULT_CONTENTIDS_FILE
        if not cids_file.exists():
            print(f"ERROR: contentids file not found: {cids_file}", file=sys.stderr)
            sys.exit(1)
        contentids = [int(line.strip()) for line in cids_file.read_text().splitlines() if line.strip().isdigit()]
        print(f"Loaded {len(contentids)} contentids from {cids_file}", file=sys.stderr)
        cache = crawl(contentids, cache_path, args.delay)
    else:
        if not cache_path.exists():
            print(f"ERROR: cache not found: {cache_path}", file=sys.stderr)
            sys.exit(1)
        cache = json.loads(cache_path.read_text())
        print(f"Loaded {len(cache)} cache entries", file=sys.stderr)

    if not args.crawl_only:
        enrich(cache, greek_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
