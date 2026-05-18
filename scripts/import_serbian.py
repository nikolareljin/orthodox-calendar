#!/usr/bin/env python3
"""
Import Serbian Orthodox Church saints from Wikipedia.

Source: https://en.wikipedia.org/wiki/List_of_saints_of_the_Serbian_Orthodox_Church

The table has columns:
  Image | Name | Died (Year) | Feast Day (NS/OS) | Notes

Feast Day format: "4 July [O.S. 21 June]"
  NS = New Style (Gregorian), O.S. = Old Style (Julian)

The Serbian church uses the Julian calendar, so we store the O.S. (Julian) date.

Usage:
    python3 scripts/import_serbian.py --out backend/app/data/traditions/serbian_saints.json
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_saints_of_the_Serbian_Orthodox_Church"
_HEADERS = {"User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# OS date pattern: "[O.S. 21 June]" or "O.S. June 21"
_OS_RE = re.compile(
    r"O\.S\.\s*(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"|O\.S\.\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
    re.IGNORECASE,
)
# Fallback: first bare date "21 June" or "June 21"
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"|(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
    re.IGNORECASE,
)

_FEAST_TYPE_HINTS = [
    (re.compile(r"hieromartyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr|new-martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"venerable", re.I), "Venerable"),
    (re.compile(r"confessor|hieroconfessor", re.I), "Confessor"),
    (re.compile(r"right.believing|righteous", re.I), "Righteous"),
    (re.compile(r"equal.to.apostles?", re.I), "Equal-to-Apostles"),
    (re.compile(r"apostle", re.I), "Apostle"),
    (re.compile(r"archbishop|patriarch|bishop|metropolitan", re.I), "Hierarch"),
    (re.compile(r"prince|king|queen|tsar|despot", re.I), "Righteous"),
    (re.compile(r"monk|nun|abbess|abbot", re.I), "Venerable"),
]


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _parse_date(text: str) -> str | None:
    """Extract Julian (O.S.) date → MM-DD, fallback to first date found."""
    text = text.replace("&#160;", " ").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)

    # Try O.S. date first
    m = _OS_RE.search(text)
    if m:
        if m.group(1):
            day, month_name = int(m.group(1)), m.group(2).lower()
        else:
            month_name, day = m.group(3).lower(), int(m.group(4))
        month = _MONTH_MAP.get(month_name)
        if month:
            return f"{month:02d}-{day:02d}"

    # Fallback: first bare date
    m = _DATE_RE.search(text)
    if m:
        if m.group(1):
            day, month_name = int(m.group(1)), m.group(2).lower()
        else:
            month_name, day = m.group(3).lower(), int(m.group(4))
        month = _MONTH_MAP.get(month_name)
        if month:
            return f"{month:02d}-{day:02d}"

    return None


def _feast_type(notes: str) -> str:
    for pattern, ft in _FEAST_TYPE_HINTS:
        if pattern.search(notes):
            return ft
    return "Saint"


def _clean_name(raw: str) -> str:
    """Extract English saint name (first line before Serbian Cyrillic/Latin)."""
    raw = _strip_tags(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    # Name ends before the first Cyrillic character
    cyrillic_match = re.search(r"[А-Яа-яЁёЂЉЊЋЏђљњћџ]", raw)
    if cyrillic_match:
        raw = raw[:cyrillic_match.start()].strip()
    # Also strip trailing transliteration in Latin (often a repeat of English name)
    # Keep only up to first parenthetical or comma
    raw = re.split(r"[,(]", raw)[0].strip()
    return raw


def _year_canonized(notes: str) -> int | None:
    m = re.search(r"canon(?:ized|ised)\s+(?:in\s+)?(\d{4})", notes, re.I)
    if m:
        return int(m.group(1))
    # Also look for "glorified YYYY"
    m = re.search(r"glorif(?:ied|y)\s+(?:in\s+)?(\d{4})", notes, re.I)
    return int(m.group(1)) if m else None


def scrape_wikipedia() -> list[dict]:
    req = urllib.request.Request(WIKI_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Extract first wikitable
    table_start = html.find('<table class="wikitable')
    if table_start == -1:
        table_start = html.find("<table")
    table_end = html.find("</table>", table_start) + 8
    table_html = html[table_start:table_end]

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
    saints: list[dict] = []

    for row in rows[1:]:  # skip header
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        if len(cells) < 4:
            continue

        # cols: 0=image, 1=name, 2=died, 3=feast, 4=notes
        name_raw = cells[1] if len(cells) > 1 else ""
        feast_raw = cells[3] if len(cells) > 3 else ""
        notes_raw = cells[4] if len(cells) > 4 else ""

        name = _clean_name(name_raw)
        if not name or len(name) < 3:
            continue

        month_day = _parse_date(feast_raw)
        if not month_day:
            print(f"  SKIP (no date): {name[:50]}", file=sys.stderr)
            continue

        notes_text = _strip_tags(notes_raw).strip()
        notes_text = re.sub(r"\s+", " ", notes_text)

        died_raw = _strip_tags(cells[2]).strip() if len(cells) > 2 else ""
        died_year = re.search(r"\d{3,4}", died_raw)

        saints.append({
            "month_day": month_day,
            "name": name,
            "feast_type": _feast_type(notes_text),
            "notes": notes_text[:300] if notes_text else None,
            "year_died": int(died_year.group()) if died_year else None,
            "year_canonized": _year_canonized(notes_text),
            "wiki_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(name.replace(' ', '_'))}",
        })
        print(f"  {month_day}: {name[:60]}", file=sys.stderr)

    return saints


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Serbian Orthodox saints from Wikipedia")
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/serbian_saints.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Scraping Serbian Orthodox saints from Wikipedia...", file=sys.stderr)
    saints = scrape_wikipedia()
    print(f"  Scraped {len(saints)} saints", file=sys.stderr)

    # Group by month_day
    by_md: dict[str, list] = {}
    for s in saints:
        md = s["month_day"]
        by_md.setdefault(md, []).append({
            "name": s["name"],
            "title": s["name"],
            "feast_type": s["feast_type"],
            "hagiography_url": s["wiki_url"],
            "notes": s["notes"],
            "canonized_by": "Serbian Orthodox Church",
            "canonization_scope": "local",
            "year_canonized": s["year_canonized"],
        })

    output = [
        {
            "month_day": md,
            "tradition": "serbian",
            "calendar": "julian",
            "saints": saints_list,
        }
        for md, saints_list in sorted(by_md.items())
    ]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} saints) to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
