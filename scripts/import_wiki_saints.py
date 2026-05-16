#!/usr/bin/env python3
"""
Import tradition-specific saints from Wikipedia categories.

Uses the MediaWiki API to:
  1. List all pages in a Wikipedia category (e.g. "Category:Greek Orthodox saints")
  2. Fetch each page's wikitext and extract feast date from the infobox
  3. Output CalendarEntry JSON

Usage:
    # Greek Orthodox saints
    python3 scripts/import_wiki_saints.py \
        --category "Greek Orthodox saints" \
        --tradition greek \
        --calendar revised \
        --canonized-by "Church of Greece" \
        --scope local \
        --out backend/app/data/traditions/greek_saints.json

    # Georgian Orthodox saints
    python3 scripts/import_wiki_saints.py \
        --category "Georgian Orthodox saints" \
        --tradition georgian \
        --calendar julian \
        --canonized-by "Georgian Orthodox and Apostolic Church" \
        --scope local \
        --out backend/app/data/traditions/georgian_saints.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_FEAST_PARAMS = re.compile(
    r"\|\s*(?:feast_day|feast_date|feast|venerated_date|death_date_and_age|death_date)\s*=\s*([^\n|}{]+)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.?"
    r"|(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.?\s+(\d{1,2})",
    re.IGNORECASE,
)
_FEAST_TYPE_RE = [
    (re.compile(r"hieromartyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"venerable", re.I), "Venerable"),
    (re.compile(r"confessor", re.I), "Confessor"),
    (re.compile(r"equal.to.apostles?", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle\b", re.I), "Apostle"),
    (re.compile(r"archbishop|patriarch|bishop|metropolitan|pope", re.I), "Hierarch"),
    (re.compile(r"righteous|right.believing|king|queen|prince|emperor", re.I), "Righteous"),
]


def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def list_category_members(category: str) -> list[str]:
    """Return all page titles in a Wikipedia category."""
    titles: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "page",
        "cmlimit": "500",
    }
    while True:
        data = _api_get(params)
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
    return titles


def fetch_wikitext(title: str) -> str:
    data = _api_get({
        "action": "parse",
        "page": title,
        "prop": "wikitext",
    })
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def _parse_feast_date(wikitext: str) -> str | None:
    for m in _FEAST_PARAMS.finditer(wikitext):
        raw = m.group(1).strip()
        # Strip wikilinks [[X|Y]] → Y or X
        raw = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", raw)
        # Strip templates {{...}}
        raw = re.sub(r"\{\{[^}]+\}\}", "", raw).strip()
        # Skip if it looks like a death date (has year > 1000)
        if re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", raw) and "feast" not in m.group(0).lower():
            continue

        dm = _DATE_RE.search(raw)
        if dm:
            if dm.group(1):
                day = int(dm.group(1))
                month = _MONTH_MAP.get(dm.group(2).lower())
            else:
                month = _MONTH_MAP.get(dm.group(3).lower())
                day = int(dm.group(4))
            if month and 1 <= day <= 31:
                return f"{month:02d}-{day:02d}"
    return None


def _feast_type_from_wikitext(wikitext: str) -> str:
    # Check infobox type and categories
    for pattern, ft in _FEAST_TYPE_RE:
        if pattern.search(wikitext[:3000]):
            return ft
    return "Saint"


def _short_description(wikitext: str) -> str | None:
    """Extract first sentence of article as a short description."""
    # Remove templates and wikilinks for cleaner text
    text = re.sub(r"\{\{[^}]+\}\}", "", wikitext)
    text = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"==+[^=]+=+", "", text)
    # Find first substantive paragraph (not infobox)
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("|") and not line.startswith("!") and \
                not line.startswith("{") and not line.startswith("=") and len(line) > 60:
            # Get first sentence
            sentence = re.split(r"\.\s", line)[0].strip()
            if len(sentence) > 30:
                return sentence[:250]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import saints from Wikipedia category")
    parser.add_argument("--category", required=True, help="Wikipedia category name (without 'Category:' prefix)")
    parser.add_argument("--tradition", required=True, help="Tradition key (e.g. 'greek', 'georgian')")
    parser.add_argument("--calendar", default="gregorian", choices=["gregorian", "julian", "revised"],
                        help="Calendar system for stored dates")
    parser.add_argument("--canonized-by", required=True, help="Canonizing church name")
    parser.add_argument("--scope", default="local", choices=["local", "oriental", "pan-orthodox"],
                        help="Canonization scope")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API requests")
    parser.add_argument("--out", required=True, help="Output JSON file path")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Listing Wikipedia category: {args.category}...", file=sys.stderr)
    titles = list_category_members(args.category)
    print(f"  Found {len(titles)} pages", file=sys.stderr)

    by_md: dict[str, list] = {}
    skipped = 0

    for title in titles:
        time.sleep(args.delay)
        try:
            wikitext = fetch_wikitext(title)
            if not wikitext:
                skipped += 1
                continue

            md = _parse_feast_date(wikitext)
            if not md:
                print(f"  SKIP (no feast date): {title}", file=sys.stderr)
                skipped += 1
                continue

            desc = _short_description(wikitext)
            wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"

            saint = {
                "name": title,
                "title": title,
                "feast_type": _feast_type_from_wikitext(wikitext),
                "hagiography_url": wiki_url,
                "notes": desc,
                "canonized_by": args.canonized_by,
                "canonization_scope": args.scope,
                "year_canonized": None,
            }
            by_md.setdefault(md, []).append(saint)
            print(f"  {md}: {title[:60]}", file=sys.stderr)

        except Exception as exc:
            print(f"  ERROR {title}: {exc}", file=sys.stderr)
            skipped += 1

    output = [
        {
            "month_day": md,
            "tradition": args.tradition,
            "calendar": args.calendar,
            "saints": saints_list,
        }
        for md, saints_list in sorted(by_md.items())
    ]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} saints) to {out_path}", file=sys.stderr)
    print(f"Skipped {skipped} pages (no feast date or error)", file=sys.stderr)


if __name__ == "__main__":
    main()
