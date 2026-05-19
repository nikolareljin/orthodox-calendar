#!/usr/bin/env python3
"""
Import Romanian Orthodox Church saints from Wikipedia categories.

Sources:
  - Category:Romanian_saints
  - Category:Romanian_saints_of_the_Eastern_Orthodox_Church
  - Category:Romanian_New_Martyrs

For each saint page, extracts the feast_day from the infobox wikitext,
falls back to body text date patterns, then to a second Wikipedia parse pass.

Calendar: Revised Julian (same MM-DD as Gregorian; Romania adopted New Calendar 1924).

Usage:
    python3 scripts/import_romanian.py --out backend/app/data/traditions/romanian_saints.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_HEADERS = {"User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Romanian month names
_MONTH_MAP_RO = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}

_DATE_RE = re.compile(
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august"
    r"|september|october|november|december)"
    r"|(?:january|february|march|april|may|june|july|august"
    r"|september|october|november|december)\s+(\d{1,2})",
    re.IGNORECASE,
)

_FEAST_TYPE_HINTS = [
    (re.compile(r"hieromartyr|priest.martyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr|new-martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"venerable|monastic|hermit|monk", re.I), "Venerable"),
    (re.compile(r"confessor", re.I), "Confessor"),
    (re.compile(r"equal.to.apostles?", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle", re.I), "Apostle"),
    (re.compile(r"bishop|metropolitan|archbishop|patriarch|hierarch", re.I), "Hierarch"),
    (re.compile(r"prince|voivode|hospodar|king|ruler|voivod", re.I), "Righteous"),
    (re.compile(r"righteous|right.believing", re.I), "Righteous"),
]


def _wiki_get(params: dict) -> dict:
    params["format"] = "json"
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _cat_pages(category: str) -> list[str]:
    data = _wiki_get({
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": "500",
        "cmtype": "page",
    })
    return [m["title"] for m in data.get("query", {}).get("categorymembers", [])]


def _extract_date_from_wikitext(wikitext: str) -> str | None:
    """Pull feast_day from infobox, then fall back to body text dates."""
    # Infobox feast_day parameter
    m = re.search(r"\|\s*feast_day\s*=\s*([^\n|}{]+)", wikitext, re.IGNORECASE)
    if m:
        val = re.sub(r"\{\{[^}]*\}\}", " ", m.group(1))  # strip templates
        val = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", val)  # strip wikilinks
        val = re.sub(r"<[^>]+>", " ", val)
        dm = _DATE_RE.search(val)
        if dm:
            if dm.group(1):
                day, month_name = int(dm.group(1)), dm.group(2).lower()
            else:
                month_name, day = dm.group(0).split()[0].lower(), int(dm.group(3))
            month = _MONTH_MAP.get(month_name)
            if month:
                return f"{month:02d}-{day:02d}"

    # Body text: first date match (usually in the lead paragraph)
    clean = re.sub(r"\{\{[^}]*\}\}", " ", wikitext)
    clean = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", clean)
    dm = _DATE_RE.search(clean)
    if dm:
        if dm.group(1):
            day, month_name = int(dm.group(1)), dm.group(2).lower()
        else:
            month_name, day = dm.group(0).split()[0].lower(), int(dm.group(3))
        month = _MONTH_MAP.get(month_name)
        if month:
            return f"{month:02d}-{day:02d}"

    return None


def _fetch_saint(title: str) -> dict | None:
    """Fetch wikitext + extract of a Wikipedia page."""
    data = _wiki_get({
        "action": "query",
        "titles": title,
        "prop": "revisions|extracts",
        "rvprop": "content",
        "rvslots": "main",
        "exintro": "1",
        "explaintext": "1",
        "exsectionformat": "plain",
    })
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    if page.get("missing") is not None:
        return None

    wikitext = (
        page.get("revisions", [{}])[0]
        .get("slots", {})
        .get("main", {})
        .get("*", "")
    )
    extract = page.get("extract", "")
    return {"wikitext": wikitext, "extract": extract, "pageid": page.get("pageid")}


def _feast_type(name: str, extract: str) -> str:
    combined = f"{name} {extract}"
    for pattern, ft in _FEAST_TYPE_HINTS:
        if pattern.search(combined):
            return ft
    return "Saint"


def _year_canonized(wikitext: str) -> int | None:
    m = re.search(r"canon(?:ized|ised|ization)\D{0,20}(\d{4})", wikitext, re.I)
    return int(m.group(1)) if m else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Romanian Orthodox saints from Wikipedia")
    parser.add_argument("--out", default="backend/app/data/traditions/romanian_saints.json")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Gather saint names from all relevant categories
    cats = [
        "Romanian_saints",
        "Romanian_saints_of_the_Eastern_Orthodox_Church",
        "Romanian_New_Martyrs",
    ]
    titles: set[str] = set()
    for cat in cats:
        found = _cat_pages(cat)
        print(f"  Category:{cat} → {len(found)} pages", file=sys.stderr)
        titles.update(found)

    # Also add known saints not in categories
    extra = [
        "Paisius Velichkovsky",
        "Peter Movilă",
        "Philaret of Moscow",
    ]
    titles.update(extra)

    print(f"\nFetching {len(titles)} saint pages...", file=sys.stderr)

    by_md: dict[str, list] = {}
    skipped = 0

    for title in sorted(titles):
        time.sleep(args.delay)
        data = _fetch_saint(title)
        if not data:
            print(f"  SKIP (not found): {title}", file=sys.stderr)
            skipped += 1
            continue

        month_day = _extract_date_from_wikitext(data["wikitext"])
        if not month_day:
            print(f"  SKIP (no date):   {title}", file=sys.stderr)
            skipped += 1
            continue

        extract = data["extract"] or ""
        notes = re.sub(r"\s+", " ", extract.strip())[:400] or None
        year_can = _year_canonized(data["wikitext"])
        ft = _feast_type(title, extract)

        # Clean title: strip disambiguation suffixes like "(bishop)"
        clean_name = re.sub(r"\s*\([^)]+\)\s*$", "", title).strip()
        clean_name = clean_name.replace("Saint ", "").strip()

        saint_entry = {
            "name": clean_name,
            "title": clean_name,
            "feast_type": ft,
            "hagiography_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
            "notes": notes,
            "canonized_by": "Romanian Orthodox Church",
            "canonization_scope": "local",
            "year_canonized": year_can,
        }
        by_md.setdefault(month_day, []).append(saint_entry)
        print(f"  {month_day}  {clean_name[:55]}", file=sys.stderr)

    output = [
        {
            "month_day": md,
            "tradition": "romanian",
            "calendar": "revised",
            "saints": saints_list,
        }
        for md, saints_list in sorted(by_md.items())
    ]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(
        f"\nWrote {len(output)} entries ({total} saints, {skipped} skipped) → {out_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
