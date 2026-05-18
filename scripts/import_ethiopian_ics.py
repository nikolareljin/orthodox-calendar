#!/usr/bin/env python3
"""
Import Ethiopian Orthodox Tewahedo Church saint days from a public Google Calendar ICS feed.

Source: EOTC Saint Days calendar (created by blainhaile@gmail.com)
ICS URL: https://calendar.google.com/calendar/ical/<CALENDAR_ID>/public/basic.ics

The calendar encodes 30 saints representing the monthly Ge'ez synaxarion:
each saint is commemorated on the same numbered day (1-30) of every Ge'ez
month (30-day months). Events appear with RRULE:FREQ=DAILY;INTERVAL=30.

Gregorian mapping: Day N → Sep 11 + (N-1) days  (using Meskerem as canonical month)
  Day 1  = Sep 11  (Meskerem 1, start of Ethiopian year)
  Day 30 = Oct 10  (Meskerem 30)

Usage:
    python3 scripts/import_ethiopian_ics.py \
        --out backend/app/data/traditions/ethiopian_saints.json

    python3 scripts/import_ethiopian_ics.py --merge \
        --out backend/app/data/traditions/ethiopian_saints.json

    python3 scripts/import_ethiopian_ics.py --no-enrich \
        --out backend/app/data/traditions/ethiopian_saints.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "58ea5e6e0f1ac27b7be6d46920b36c87943d314f16076823dd9d45c34f095391"
    "%40group.calendar.google.com/public/basic.ics"
)

WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

# Meskerem 1 = Sep 11 (canonical Gregorian anchor for Ge'ez month day 1)
_MESKEREM_1 = date(2024, 9, 11)

# Ge'ez title prefixes → feast_type
_TITLE_TYPE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bkidist\b", re.I), "Virgin"),   # feminine saint
    (re.compile(r"\bkidus\b|\bqiddus\b", re.I), "Saint"),
    (re.compile(r"\babune\b|\babba\b", re.I), "Venerable"),
]

# Feast-type overrides based on known names
_NAME_TYPE_OVERRIDES: dict[str, str] = {
    "michael": "Archangel", "gebriel": "Archangel", "gabriel": "Archangel",
    "ruphael": "Archangel", "raphael": "Archangel", "urael": "Archangel",
    "uriel": "Archangel",
    "giorgis": "Martyr", "george": "Martyr",
    "merkorios": "Martyr", "mercurius": "Martyr",
    "estifanos": "Martyr", "stephen": "Martyr",
    "kirkos": "Martyr",
    "arsema": "Martyr",
    "thaddeus": "Apostle",
    "thomas": "Apostle",
    "petros": "Apostle", "paulos": "Apostle",
}

# Ge'ez name → Wikipedia page title for enrichment
_WIKI_MAP: dict[str, str] = {
    "kidus michael": "Michael (archangel)",
    "kidus gebriel": "Gabriel",
    "kidus ruphael": "Raphael (archangel)",
    "kidus urael": "Uriel",
    "kidus giorgis": "Saint George",
    "kidus merkorios": "Mercurius of Caesarea",
    "kidus estifanos": "Saint Stephen",
    "kidus kirkos": "Cyricus and Julitta",
    "kidis arsema": "Hripsime",
    "kidist arsema": "Hripsime",
    "kidist dingle mariam": "Mary, mother of Jesus",
    "kidist selassie": "Trinity",
    "kidist kidanemihret": "Kidane Mehret",
    "abune teklehaimanot": "Takla Haymanot",
    "abune aregawi": "Za-Mikael Aregawi",
    "abune gebre menfes kidus": "Gäbrä Mänfäs Qiddus",
    "abune zenamarkos": "Zena Markos",
    "abune habtemaria": "Habta Maryam",
    "kidus medhanialem": "Christ as Savior of the World",
    "kidus emmanuel": "Emmanuel (Christianity)",
    "kidus thomas": "Thomas the Apostle",
    "lideta mariam": "Nativity of Mary",
    "kidus kiros": "Cyrus of Alexandria",
    "kidus meskel": "True Cross",
    "kidus ewastateos": "Ewostatewos",
    "kidus dawit": "David",
}

# SUMMARY patterns that are NOT saints (personal events, placeholders)
_NOISE_RE = re.compile(
    r"^(?:new event|ethio|last day|go to|lunch)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# ICS parsing
# ---------------------------------------------------------------------------

def fetch_ics(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ics(content: str) -> list[dict]:
    """
    Extract unique saint entries from ICS VEVENTs.
    Returns list of {geez_day, name, raw_summary} dicts, deduped by geez_day.
    """
    vevent_re = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
    summary_re = re.compile(r"SUMMARY:(.+)", re.MULTILINE)
    day_re = re.compile(r"^(\d+)(?:st|nd|rd|th)?[\.\:]")

    seen_days: set[int] = set()
    entries: list[dict] = []

    for vevent in vevent_re.finditer(content):
        block = vevent.group(1)
        sm = summary_re.search(block)
        if not sm:
            continue
        summary = sm.group(1).strip()

        # Skip non-saint events
        if _NOISE_RE.match(summary):
            continue
        dm = day_re.match(summary)
        if not dm:
            continue

        geez_day = int(dm.group(1))
        if geez_day < 1 or geez_day > 30:
            continue
        if geez_day in seen_days:
            continue
        seen_days.add(geez_day)

        # Strip day prefix and trailing emoji/symbols
        name = re.sub(r"^\d+(?:st|nd|rd|th)?[\.\:]\s*", "", summary).strip()
        name = re.sub(r"\s*[✟✝☩]\s*$", "", name).strip()
        # Normalize whitespace
        name = re.sub(r"\s+", " ", name)

        entries.append({"geez_day": geez_day, "name": name, "raw_summary": summary})

    return sorted(entries, key=lambda e: e["geez_day"])


def geez_day_to_gregorian(day: int) -> str:
    """Map Ge'ez calendar day (1-30) to Gregorian MM-DD using Meskerem reference."""
    d = _MESKEREM_1 + timedelta(days=day - 1)
    return d.strftime("%m-%d")


def _feast_type(name: str) -> str:
    lower = name.lower()
    for w, ft in _NAME_TYPE_OVERRIDES.items():
        if w in lower:
            return ft
    for pattern, ft in _TITLE_TYPE:
        if pattern.search(name):
            return ft
    return "Saint"


def _wiki_key(name: str) -> str | None:
    """Return a Wikipedia title for this name, or None."""
    lower = name.lower()
    # Direct map
    for key, title in _WIKI_MAP.items():
        if key in lower:
            return title
    return None


# ---------------------------------------------------------------------------
# Wikipedia enrichment
# ---------------------------------------------------------------------------

def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _extract_text(page: dict) -> str | None:
    if page.get("missing") is not None:
        return None
    raw = (page.get("extract") or "").strip()
    if len(raw) < 30:
        return None
    if "may refer to:" in raw or "disambiguation" in raw.lower():
        return None
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    return " ".join(sentences[:3])[:400].strip()


def fetch_extracts(titles: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        try:
            data = _api_get({
                "action": "query",
                "titles": "|".join(batch),
                "prop": "extracts",
                "exintro": "1",
                "exsentences": "3",
                "explaintext": "1",
                "redirects": "1",
            })
        except Exception as exc:
            print(f"  WARN: {exc}", file=sys.stderr)
            continue

        norm: dict[str, str] = {}
        for r in data.get("query", {}).get("redirects", []) + data.get("query", {}).get("normalized", []):
            norm[r["from"]] = r["to"]

        for page in data.get("query", {}).get("pages", {}).values():
            desc = _extract_text(page)
            if not desc:
                continue
            title = page.get("title", "")
            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            result[title] = {"description": desc, "url": url}

        for orig in batch:
            resolved = norm.get(orig, orig)
            if resolved in result and orig not in result:
                result[orig] = result[resolved]

        if i + 50 < len(titles):
            time.sleep(0.3)

    return result


# ---------------------------------------------------------------------------
# Build output
# ---------------------------------------------------------------------------

def build_output(entries: list[dict], enrichment: dict[str, dict]) -> list[dict]:
    by_md: dict[str, list] = {}

    for e in entries:
        md = geez_day_to_gregorian(e["geez_day"])
        wiki_key = _wiki_key(e["name"])
        enrich = enrichment.get(wiki_key, {}) if wiki_key else {}

        saint = {
            "name": e["name"],
            "title": e["name"],
            "feast_type": _feast_type(e["name"]),
            "hagiography_url": enrich.get("url") or None,
            "notes": enrich.get("description") or (
                f"Ethiopian Orthodox Tewahedo Church — commemorated on the "
                f"{e['geez_day']}th of every Geʼez month"
            ),
            "canonized_by": "Ethiopian Orthodox Tewahedo Church",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        by_md.setdefault(md, []).append(saint)

    return [
        {"month_day": md, "tradition": "ethiopian", "calendar": "gregorian", "saints": saints}
        for md, saints in sorted(by_md.items())
    ]


def merge_outputs(existing: list[dict], new: list[dict]) -> list[dict]:
    by_md: dict[str, dict] = {e["month_day"]: e for e in existing}
    for entry in new:
        md = entry["month_day"]
        if md not in by_md:
            by_md[md] = entry
        else:
            seen = {s["name"] for s in by_md[md]["saints"]}
            for saint in entry["saints"]:
                if saint["name"] not in seen:
                    by_md[md]["saints"].append(saint)
                    seen.add(saint["name"])
    return [by_md[md] for md in sorted(by_md)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Import EOTC saint days from Google Calendar ICS")
    parser.add_argument("--out", default="backend/app/data/traditions/ethiopian_saints.json")
    parser.add_argument("--merge", action="store_true",
                        help="Merge into existing file instead of replacing")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Skip Wikipedia enrichment")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching ICS from Google Calendar...", file=sys.stderr)
    content = fetch_ics(ICS_URL)
    print("  Parsing saint events...", file=sys.stderr)

    entries = parse_ics(content)
    print(f"  Found {len(entries)} unique saints (days 1-30)", file=sys.stderr)
    for e in entries:
        md = geez_day_to_gregorian(e["geez_day"])
        print(f"    Day {e['geez_day']:2d} ({md}): {e['name']}", file=sys.stderr)

    enrichment: dict[str, dict] = {}
    if not args.no_enrich:
        wiki_titles = list({t for e in entries if (t := _wiki_key(e["name"]))})
        print(f"\n  Enriching {len(wiki_titles)} saints via Wikipedia...", file=sys.stderr)
        enrichment = fetch_extracts(wiki_titles)
        print(f"  Got {len(enrichment)} descriptions", file=sys.stderr)

    output = build_output(entries, enrichment)

    if args.merge and out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            existing = json.load(f)
        output = merge_outputs(existing, output)
        print(f"  Merged with {len(existing)} existing entries", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    enriched = sum(
        1 for e in output for s in e["saints"]
        if s.get("hagiography_url")
    )
    print(f"\nWrote {len(output)} entries ({total} saints, {enriched} enriched) → {out_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
