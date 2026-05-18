#!/usr/bin/env python3
"""
Import Ethiopian Orthodox Tewahedo Church saints from Wikipedia.

Sources combined:
  1. "Calendar of saints (Orthodox Tewahedo)" — monthly table (days 1-30)
     and annual fixed feasts
  2. "Category:Ethiopian saints" — individual saint pages with infobox feast dates

Monthly saints (days 1-30) are mapped to Gregorian using Meskerem as the
canonical reference month: Day N → Sep 11 + (N-1) days.

Usage:
    python3 scripts/import_ethiopian_wiki.py \
        --out backend/app/data/traditions/ethiopian_saints.json

    python3 scripts/import_ethiopian_wiki.py --merge \
        --out backend/app/data/traditions/ethiopian_saints.json

    python3 scripts/import_ethiopian_wiki.py --no-enrich \
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

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_CALENDAR_PAGE = "Calendar of saints (Orthodox Tewahedo)"
WIKI_URL_BASE = "https://en.wikipedia.org/wiki/Calendar_of_saints_(Orthodox_Tewahedo)"

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

def _meskerem_1_for(anchor_year: int) -> date:
    """Return the Gregorian date of Meskerem 1 for the given Gregorian year.

    Falls on Sep 12 when anchor_year+1 is a Gregorian leap year (divisible by 4,
    except centuries not divisible by 400), Sep 11 otherwise.
    """
    next_year = anchor_year + 1
    is_next_leap = next_year % 4 == 0 and (next_year % 100 != 0 or next_year % 400 == 0)
    return date(anchor_year, 9, 12 if is_next_leap else 11)

# Canonical anchor year for the dataset. Override with --anchor-year for a different cycle.
_MESKEREM_1 = _meskerem_1_for(2024)

# Ethiopian months for parsing annual feast section
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

_FEAST_TYPE_HINTS = [
    (re.compile(r"hieromartyr", re.I), "Hieromartyr"),
    (re.compile(r"new martyr", re.I), "New Martyr"),
    (re.compile(r"\bmartyr(s)?\b", re.I), "Martyr"),
    (re.compile(r"\bvirgin\b|\bour lady\b", re.I), "Virgin"),
    (re.compile(r"\bconfessor\b", re.I), "Confessor"),
    (re.compile(r"archangel\b", re.I), "Archangel"),
    (re.compile(r"\bapostle(s)?\b|\bevangelist\b", re.I), "Apostle"),
    (re.compile(r"patriarch|bishop|metropolitan|deacon|priest", re.I), "Hierarch"),
    (re.compile(r"abuna\b|abba\b|monk\b|hermit\b|monastic", re.I), "Venerable"),
    (re.compile(r"prophet|elijah|elias", re.I), "Prophet"),
    (re.compile(r"trinity|god the father|god the son|savior|immanuel|emmanuel", re.I), "Great Feast"),
    (re.compile(r"feast|cross|nativity|epiphany|assumption|presentation|annunciation", re.I), "Feast"),
]

# Targets to skip for enrichment (too generic)
_SKIP_TARGETS = frozenset({
    "egypt", "temple of jerusalem", "apostles in the new testament",
    "sons of thunder (christianity)", "holy virgin mary",
    "names and titles of jesus in the new testament#emmanuel",
    "cyrus the great in the bible", "feast of the cross",
})

_INFOBOX_FEAST_RE = re.compile(
    r"\|\s*(?:feast_day|feast_date|feast|venerated_date)\s*=\s*([^\n|}{]+)",
    re.IGNORECASE,
)


def _infobox_text(wikitext: str) -> str:
    """Extract the first {{Infobox ...}} block by counting brace depth."""
    for prefix in ("{{Infobox", "{{infobox"):
        start = wikitext.find(prefix)
        if start != -1:
            break
    else:
        return wikitext[:3000]
    depth, i = 0, start
    while i < len(wikitext):
        if wikitext[i:i+2] == "{{":
            depth += 1
            i += 2
        elif wikitext[i:i+2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start:i]
        else:
            i += 1
    return wikitext[start:start + 3000]
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"|(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
    re.IGNORECASE,
)


def _feast_type(name: str) -> str:
    for pattern, ft in _FEAST_TYPE_HINTS:
        if pattern.search(name):
            return ft
    return "Saint"


def _strip_wikilinks(text: str) -> str:
    return re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", text).strip()


def _extract_wikilinks(raw: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(raw)]


def _best_target(targets: list[str]) -> str | None:
    for t in targets:
        if t.lower() not in _SKIP_TARGETS and not t.startswith("Category:") and not t.startswith("File:"):
            return t
    return None


def geez_day_to_gregorian(day: int) -> str:
    d = _MESKEREM_1 + timedelta(days=day - 1)
    return d.strftime("%m-%d")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _fetch_wikitext(page: str) -> str:
    data = _api_get({"action": "parse", "page": page, "prop": "wikitext"})
    return data["parse"]["wikitext"]["*"]


def _extract_desc(page: dict) -> str | None:
    if page.get("missing") is not None:
        return None
    raw = (page.get("extract") or "").strip()
    if len(raw) < 30 or "may refer to:" in raw or "disambiguation" in raw.lower():
        return None
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    return " ".join(sentences[:3])[:400].strip()


def fetch_extracts(titles: list[str], delay: float = 0.3) -> dict[str, dict]:
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
            desc = _extract_desc(page)
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
            time.sleep(delay)

    return result


# ---------------------------------------------------------------------------
# Parse the monthly wikitable (days 1-30)
# ---------------------------------------------------------------------------

def parse_monthly_table(wikitext: str) -> list[dict]:
    """
    Parse the wikitable in 'Calendar of saints (Orthodox Tewahedo)'.
    Returns list of {geez_day, name, wiki_targets, month_day}.
    """
    # Find the wikitable section
    table_re = re.compile(r"\{\|.*?\|\}", re.DOTALL)
    row_re = re.compile(r"\|\-\s*\n\|(\d+)(?:st|nd|rd|th)?\s*\n\|(.+?)(?=\n\|-|\n\|\})", re.DOTALL)

    entries: list[dict] = []
    table_m = table_re.search(wikitext)
    if not table_m:
        return entries

    table = table_m.group(0)
    for m in row_re.finditer(table):
        day = int(m.group(1))
        raw = m.group(2).strip()
        # Remove ref tags
        raw = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"<ref[^>]*/?>", "", raw)
        # Remove {{...}} templates
        raw = re.sub(r"\{\{[^}]+\}\}", "", raw)

        wiki_targets = _extract_wikilinks(raw)
        name = _strip_wikilinks(raw).strip()
        name = re.sub(r"\s+", " ", name).strip("| \n")

        if not name:
            continue

        entries.append({
            "geez_day": day,
            "name": name,
            "wiki_targets": wiki_targets,
            "month_day": geez_day_to_gregorian(day),
        })

    return sorted(entries, key=lambda e: e["geez_day"])


# ---------------------------------------------------------------------------
# Parse annual fixed feasts
# ---------------------------------------------------------------------------

def parse_annual_feasts(wikitext: str) -> list[dict]:
    """
    Parse the annual feasts section (fixed Gregorian dates).
    Returns list of {month_day, name, wiki_targets}.
    """
    entries: list[dict] = []
    # Find "==Annual feasts==" section
    section_m = re.search(r"==Annual feasts?\s*==\s*\n(.*?)(?=\n==|\Z)", wikitext, re.DOTALL | re.IGNORECASE)
    if not section_m:
        return entries

    section = section_m.group(1)
    # Match: "* Month Day – Name" or "* Month Day and Month Day – Name"
    bullet_re = re.compile(r"^\*\s+(.+)$", re.MULTILINE)

    for m in bullet_re.finditer(section):
        raw = m.group(1).strip()
        # Strip refs
        raw = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"<ref[^>]*/?>", "", raw)

        # Find "Month Day –" pattern
        date_m = re.search(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+)",
            raw, re.IGNORECASE
        )
        if not date_m:
            continue

        month = _MONTH_NAMES[date_m.group(1).lower()]
        day = int(date_m.group(2))
        month_day = f"{month:02d}-{day:02d}"

        # Name is after the "–" dash
        dash_m = re.search(r"[–—-]\s*(.+)", raw)
        name_raw = dash_m.group(1).strip() if dash_m else _strip_wikilinks(raw)
        wiki_targets = _extract_wikilinks(name_raw)
        name = _strip_wikilinks(name_raw)
        name = re.sub(r"\s+", " ", name).strip()

        if name:
            entries.append({
                "month_day": month_day,
                "name": name,
                "wiki_targets": wiki_targets,
            })

    return entries


# ---------------------------------------------------------------------------
# Parse individual saint category pages for feast dates
# ---------------------------------------------------------------------------

def parse_category_saints(delay: float = 0.5) -> list[dict]:
    """
    List all pages in Category:Ethiopian saints and extract feast dates
    from their wikitext infoboxes.
    """
    entries: list[dict] = []

    # List category members
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Ethiopian saints",
        "cmtype": "page",
        "cmlimit": "500",
    }
    data = _api_get(params)
    titles = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    # Remove template pages
    titles = [t for t in titles if not t.startswith("Template:")]
    print(f"  Category:Ethiopian saints → {len(titles)} pages", file=sys.stderr)

    for title in titles:
        time.sleep(delay)
        try:
            wikitext = _fetch_wikitext(title)
        except Exception as exc:
            print(f"    SKIP {title}: {exc}", file=sys.stderr)
            continue

        # Extract feast date from infobox only (avoid navboxes/citations)
        md = None
        for fm in _INFOBOX_FEAST_RE.finditer(_infobox_text(wikitext)):
            raw = fm.group(1).strip()
            raw = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", raw)
            raw = re.sub(r"\{\{[^}]+\}\}", "", raw).strip()
            if re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", raw) and "feast" not in fm.group(0).lower():
                continue
            dm = _DATE_RE.search(raw)
            if dm:
                if dm.group(1):
                    day, month = int(dm.group(1)), _MONTH_NAMES.get(dm.group(2).lower())
                else:
                    month, day = _MONTH_NAMES.get(dm.group(3).lower()), int(dm.group(4))
                if month and 1 <= day <= 31:
                    md = f"{month:02d}-{day:02d}"
                    break

        if not md:
            print(f"    SKIP (no feast date): {title}", file=sys.stderr)
            continue

        wiki_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        print(f"    {md}: {title}", file=sys.stderr)
        entries.append({
            "month_day": md,
            "name": title,
            "wiki_url": wiki_url,
            "wiki_targets": [title],
        })

    return entries


# ---------------------------------------------------------------------------
# Build output
# ---------------------------------------------------------------------------

def build_output(
    monthly: list[dict],
    annual: list[dict],
    category: list[dict],
    enrichment: dict[str, dict],
) -> list[dict]:
    by_md: dict[str, list] = {}

    def _add(md: str, name: str, wiki_targets: list[str], wiki_url: str | None = None):
        target = _best_target(wiki_targets)
        enrich = enrichment.get(target, {}) if target else {}
        saint = {
            "name": name,
            "title": name,
            "feast_type": _feast_type(name),
            "hagiography_url": wiki_url or enrich.get("url") or WIKI_URL_BASE,
            "notes": enrich.get("description") or (
                "Ethiopian Orthodox Tewahedo Church"
            ),
            "canonized_by": "Ethiopian Orthodox Tewahedo Church",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        existing = by_md.setdefault(md, [])
        if not any(s["name"] == name for s in existing):
            existing.append(saint)

    for e in monthly:
        _add(e["month_day"], e["name"], e["wiki_targets"])

    for e in annual:
        _add(e["month_day"], e["name"], e["wiki_targets"])

    for e in category:
        _add(e["month_day"], e["name"], e.get("wiki_targets", []), e.get("wiki_url"))

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
    parser = argparse.ArgumentParser(description="Import Ethiopian Orthodox saints from Wikipedia")
    parser.add_argument("--out", default="backend/app/data/traditions/ethiopian_saints.json")
    parser.add_argument("--merge", action="store_true",
                        help="Merge into existing file instead of replacing")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Skip Wikipedia extract enrichment")
    parser.add_argument("--no-category", action="store_true",
                        help="Skip individual saint category scraping")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--anchor-year", type=int, default=2024,
                        help="Gregorian year used as Meskerem 1 anchor (default: 2024)")
    args = parser.parse_args()

    global _MESKEREM_1
    _MESKEREM_1 = _meskerem_1_for(args.anchor_year)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching Calendar of saints (Orthodox Tewahedo) wikitext...", file=sys.stderr)
    wikitext = _fetch_wikitext(WIKI_CALENDAR_PAGE)

    print("  Parsing monthly table (days 1-30)...", file=sys.stderr)
    monthly = parse_monthly_table(wikitext)
    print(f"    {len(monthly)} monthly entries", file=sys.stderr)

    print("  Parsing annual fixed feasts...", file=sys.stderr)
    annual = parse_annual_feasts(wikitext)
    print(f"    {len(annual)} annual feast entries", file=sys.stderr)

    category: list[dict] = []
    if not args.no_category:
        print("  Fetching Category:Ethiopian saints individual pages...", file=sys.stderr)
        category = parse_category_saints(delay=args.delay)
        print(f"    {len(category)} category saints with feast dates", file=sys.stderr)

    enrichment: dict[str, dict] = {}
    if not args.no_enrich:
        all_entries = monthly + annual + category
        targets: list[str] = []
        seen: set[str] = set()
        for e in all_entries:
            t = _best_target(e.get("wiki_targets", []))
            if t and t not in seen:
                targets.append(t)
                seen.add(t)

        print(f"\n  Enriching {len(targets)} Wikipedia pages...", file=sys.stderr)
        enrichment = fetch_extracts(targets, delay=args.delay)
        print(f"    Got {len(enrichment)} descriptions", file=sys.stderr)

    output = build_output(monthly, annual, category, enrichment)

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
        if s["notes"] and not s["notes"].startswith("Ethiopian Orthodox")
    )
    print(f"\nWrote {len(output)} entries ({total} saints, {enriched} enriched) → {out_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
