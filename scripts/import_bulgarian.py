#!/usr/bin/env python3
"""
Import Bulgarian Orthodox Church saints from Wikipedia categories.

Sources:
  - Category:Bulgarian_saints
  - Category:Medieval_Bulgarian_saints
  - Category:Bulgarian_royal_saints

Calendar: Revised Julian (Bulgaria adopted New Calendar December 1968).

Usage:
    python3 scripts/import_bulgarian.py --out backend/app/data/traditions/bulgarian_saints.json
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

_DATE_RE = re.compile(
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august"
    r"|september|october|november|december)"
    r"|(?:january|february|march|april|may|june|july|august"
    r"|september|october|november|december)\s+(\d{1,2})",
    re.IGNORECASE,
)

_FEAST_TYPE_HINTS = [
    (re.compile(r"hieromartyr|priest.martyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"venerable|monastic|hermit|monk|hesychast", re.I), "Venerable"),
    (re.compile(r"confessor", re.I), "Confessor"),
    (re.compile(r"equal.to.apostles?", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle|\bevangelizer", re.I), "Apostle"),
    (re.compile(r"bishop|metropolitan|archbishop|patriarch|exarch", re.I), "Hierarch"),
    (re.compile(r"king|tsar|prince|knyaz|ruler|sovereign", re.I), "Righteous"),
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
    m = re.search(r"\|\s*feast_day\s*=\s*([^\n|}{]+)", wikitext, re.IGNORECASE)
    if m:
        val = re.sub(r"\{\{[^}]*\}\}", " ", m.group(1))
        val = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", val)
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
    return {"wikitext": wikitext, "extract": extract}


def _feast_type(name: str, extract: str) -> str:
    combined = f"{name} {extract}"
    for pattern, ft in _FEAST_TYPE_HINTS:
        if pattern.search(combined):
            return ft
    return "Saint"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Bulgarian Orthodox saints from Wikipedia")
    parser.add_argument("--out", default="backend/app/data/traditions/bulgarian_saints.json")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cats = [
        "Bulgarian_saints",
        "Medieval_Bulgarian_saints",
        "Bulgarian_royal_saints",
    ]
    titles: set[str] = set()
    for cat in cats:
        found = _cat_pages(cat)
        print(f"  Category:{cat} → {len(found)} pages", file=sys.stderr)
        titles.update(found)

    # Key Bulgarian saints that may not appear in categories
    extra = [
        "John of Rila",
        "Cyril and Methodius",
        "Clement of Ohrid",
        "Naum of Preslav",
        "Boris I of Bulgaria",
        "Paisius of Hilendar",
        "Sophronius of Vratsa",
        "Euthymius of Tarnovo",
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
        ft = _feast_type(title, extract)

        clean_name = re.sub(r"\s*\([^)]+\)\s*$", "", title).strip()
        clean_name = clean_name.replace("Saint ", "").strip()

        saint_entry = {
            "name": clean_name,
            "title": clean_name,
            "feast_type": ft,
            "hagiography_url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
            "notes": notes,
            "canonized_by": "Bulgarian Orthodox Church",
            "canonization_scope": "local",
            "year_canonized": None,
        }
        by_md.setdefault(month_day, []).append(saint_entry)
        print(f"  {month_day}  {clean_name[:55]}", file=sys.stderr)

    output = [
        {
            "month_day": md,
            "tradition": "bulgarian",
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
