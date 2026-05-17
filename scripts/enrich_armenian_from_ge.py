#!/usr/bin/env python3
"""
Enrich the Armenian saints data with hagiography URLs and descriptions
from armenianchurch.ge/en/kalendar-prazdnikov.

This site has 127 feast pages with individual hagiographic text but no
explicit day numbers — only month categories. Strategy:
  1. Scrape all feast name + URL pairs (grouped by month)
  2. For each feast page, extract description text from article body
  3. Match against existing armenian_saints.json entries by name similarity
  4. Update hagiography_url and notes where a confident match is found

Usage:
    python3 scripts/enrich_armenian_from_ge.py \
        --saints backend/app/data/traditions/armenian_saints.json

    python3 scripts/enrich_armenian_from_ge.py --dry-run   # preview matches
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://armenianchurch.ge"
CALENDAR_URL = f"{BASE_URL}/en/kalendar-prazdnikov"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Prefixes stripped before name comparison
_PREFIX_RE = re.compile(
    r"^(?:feast\s+of\s+(?:the\s+)?|commemoration\s+of\s+(?:the\s+)?|"
    r"birth\s+of\s+(?:the\s+)?|eve\s+of\s+(?:the\s+)?|"
    r"about\s+(?:the\s+)?|saints?\s+|sts?\.\s+|st\.\s+)",
    re.IGNORECASE,
)

_STOP_WORDS = frozenset({
    "the", "of", "and", "his", "her", "their", "our", "lord", "holy",
    "blessed", "saint", "saints", "feast", "commemoration", "day",
})


def _normalize(name: str) -> set[str]:
    """Return set of significant words from a name for fuzzy matching."""
    name = _PREFIX_RE.sub("", name).lower()
    words = re.split(r"\W+", name)
    return {w for w in words if len(w) > 3 and w not in _STOP_WORDS}


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity on significant word sets."""
    sa, sb = _normalize(a), _normalize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def scrape_feast_list() -> list[dict]:
    """
    Scrape all feast name + URL pairs from the calendar navigation.
    Returns list of {name, url, month} dicts.
    """
    html = _fetch(CALENDAR_URL)
    feasts: list[dict] = []
    seen: set[str] = set()

    # Extract links under /en/kalendar-prazdnikov/description-2/MONTH/SLUG
    link_re = re.compile(
        r'href="(/en/kalendar-prazdnikov/description-2/([a-z]+)/([^"/?]+))"[^>]*'
        r'(?:data-text|>)\s*"?([^"<]{5,100})',
        re.IGNORECASE,
    )
    # Also try data-text attribute pattern
    nav_re = re.compile(
        r'data-text="([^"]{5,120})"\s+href="(/en/kalendar-prazdnikov/description-2/([a-z]+)/([^"/?]+))"',
        re.IGNORECASE,
    )

    for m in nav_re.finditer(html):
        name, path, month, slug = m.group(1), m.group(2), m.group(3), m.group(4)
        if month not in _MONTHS or path in seen:
            continue
        seen.add(path)
        feasts.append({"name": name.strip(), "url": BASE_URL + path, "month": month, "slug": slug})

    # Fallback: parse href links
    if not feasts:
        for m in link_re.finditer(html):
            path, month, slug, name = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            if month not in _MONTHS or path in seen:
                continue
            seen.add(path)
            feasts.append({"name": name, "url": BASE_URL + path, "month": month, "slug": slug})

    return feasts


def fetch_feast_description(url: str) -> str | None:
    """Fetch feast page and extract main article text (2-3 sentences)."""
    try:
        html = _fetch(url)
    except Exception:
        return None

    # Find main article content (Joomla article body)
    body_m = re.search(
        r'<div[^>]*class="[^"]*(?:article|entry|content)[^"]*"[^>]*>(.*?)</div\s*>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not body_m:
        # Try extracting all paragraph text
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
        text_parts = [_strip_tags(p).strip() for p in paragraphs if len(p) > 80]
        if not text_parts:
            return None
        raw = " ".join(text_parts[:3])
    else:
        raw = _strip_tags(body_m.group(1))

    # Clean
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"&[a-z]+;", " ", raw)
    if len(raw) < 40:
        return None

    # First 3 sentences, cap at 400 chars
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    desc = " ".join(s for s in sentences[:3] if len(s) > 15)[:400].strip()
    return desc if len(desc) > 40 else None


def find_best_match(
    feast_name: str,
    feast_month: str,
    saints_data: list[dict],
    threshold: float = 0.3,
) -> tuple[str, dict] | None:
    """
    Find the best-matching saint entry for a given feast name + month.
    Returns (month_day, saint_dict) or None.
    """
    month_num = _MONTHS.index(feast_month.lower()) + 1
    month_prefix = f"{month_num:02d}-"

    best_score = 0.0
    best_match: tuple[str, dict] | None = None

    for entry in saints_data:
        md = entry["month_day"]
        if not md.startswith(month_prefix):
            continue
        for saint in entry["saints"]:
            score = _similarity(feast_name, saint["name"])
            if score > best_score:
                best_score = score
                best_match = (md, saint)

    if best_score >= threshold:
        return best_match
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich Armenian saints from armenianchurch.ge")
    parser.add_argument("--saints", default="backend/app/data/traditions/armenian_saints.json")
    parser.add_argument("--dry-run", action="store_true", help="Preview matches, don't write")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay between page fetches")
    parser.add_argument("--threshold", type=float, default=0.3, help="Match score threshold (0-1)")
    args = parser.parse_args()

    saints_path = Path(args.saints)
    with saints_path.open(encoding="utf-8") as f:
        saints_data = json.load(f)

    print("Scraping feast list from armenianchurch.ge...", file=sys.stderr)
    feasts = scrape_feast_list()
    print(f"  Found {len(feasts)} feast pages", file=sys.stderr)

    matched = 0
    enriched = 0

    for feast in feasts:
        time.sleep(args.delay)

        desc = fetch_feast_description(feast["url"])

        result = find_best_match(feast["name"], feast["month"], saints_data, args.threshold)

        if result:
            md, saint = result
            print(
                f"  MATCH [{feast['month'][:3]}] {feast['name'][:50]!r}\n"
                f"        → {md}: {saint['name'][:50]!r}",
                file=sys.stderr,
            )
            matched += 1
            if not args.dry_run:
                # Only update if the existing field is generic/empty
                if not saint.get("hagiography_url") or "Calendar_of_saints" in (saint.get("hagiography_url") or ""):
                    saint["hagiography_url"] = feast["url"]
                if desc and (
                    not saint.get("notes")
                    or saint["notes"].startswith("Armenian Apostolic")
                ):
                    saint["notes"] = desc
                    enriched += 1
        else:
            print(f"  NO MATCH [{feast['month'][:3]}] {feast['name'][:60]!r}", file=sys.stderr)

    if not args.dry_run:
        with saints_path.open("w", encoding="utf-8") as f:
            json.dump(saints_data, f, ensure_ascii=False, indent=2)
        print(f"\nUpdated {matched} matches, {enriched} descriptions added → {saints_path}", file=sys.stderr)
    else:
        print(f"\nDry run: {matched} potential matches found", file=sys.stderr)


if __name__ == "__main__":
    main()
