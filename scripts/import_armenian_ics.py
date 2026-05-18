#!/usr/bin/env python3
"""
Import Armenian Apostolic Church calendar from dual-language ICS files.

Sources: armenianorthodoxtheology.com — 2026 calendar in English and Armenian
  EN: https://…2026_calendar_EN.ics
  AM: https://…2026_calendar_AM.ics

Both files share identical DTSTART dates; we pair them by date to produce
bilingual entries: name (English) + name_hy (Armenian script).
Substantive entries (saints, major feasts) are kept; pure liturgical
period-counts are dropped.

Usage:
    python3 scripts/import_armenian_ics.py \\
        --out backend/app/data/traditions/armenian_saints.json

    python3 scripts/import_armenian_ics.py --merge \\
        --out backend/app/data/traditions/armenian_saints.json

    python3 scripts/import_armenian_ics.py --no-enrich --dry-run \\
        --out backend/app/data/traditions/armenian_saints.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ICS_EN = (
    "https://60550fcc-0422-43b5-a860-37640a5791e8.filesusr.com/ugd/"
    "f4ddb8_68c75a00a50d44e1a630bbbc55cc42e8.ics?dn=2026_calendar_EN.ics"
)
ICS_AM = (
    "https://60550fcc-0422-43b5-a860-37640a5791e8.filesusr.com/ugd/"
    "f4ddb8_4fed9ac96fdb48878fefae05a9fe5c16.ics?dn=2026_calendar_AM.ics"
)
ICS_REFERER = "https://www.armenianorthodoxtheology.com/armenianchurchcalendar"

WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)",
    "Referer": ICS_REFERER,
}
_WIKI_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)",
}

# ──────────────────────────────────────────────────────────
# ICS parsing
# ──────────────────────────────────────────────────────────

_VEVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
_DTSTART_RE = re.compile(r"DTSTART[^:]*:(\d{8})")
_SUMMARY_RE = re.compile(r"SUMMARY:(.+?)(?:\r?\n(?!\s)|\r?\nEND)", re.DOTALL)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_ics(content: str) -> dict[str, str]:
    """Return {MM-DD: summary} first-occurrence per date."""
    result: dict[str, str] = {}
    for m in _VEVENT_RE.finditer(content):
        block = m.group(1)
        dm = _DTSTART_RE.search(block)
        sm = _SUMMARY_RE.search(block)
        if not dm or not sm:
            continue
        raw_date = dm.group(1)            # YYYYMMDD
        md = f"{raw_date[4:6]}-{raw_date[6:8]}"
        summary = re.sub(r"\s+", " ", sm.group(1)).strip().strip('"').strip()
        if md not in result:
            result[md] = summary
    return result


# ──────────────────────────────────────────────────────────
# Name cleaning
# ──────────────────────────────────────────────────────────

# Strip ordinal prefix from English: "Xth day of Y - Saints Z" → "Saints Z"
_EN_PREFIX_RE = re.compile(
    r"^(?:(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty.?\w+|thirtieth|thirty.?\w+|"
    r"\d+(?:st|nd|rd|th)?)\s*day of\s+\S.*?)\s*[-–]\s*",
    re.IGNORECASE,
)
# Strip plain "Fast day - " prefix
_FAST_PREFIX_RE = re.compile(r"^fast\s+day\s*[-–]\s*", re.IGNORECASE)

# Armenian ordinal prefix: "Ե. օր Պահոց Ծննդեան։" → strip to saint name
# Pattern: Armenian letter(s) + dot + space + Armenian words + Armenian full stop ։
_HY_PREFIX_RE = re.compile(r"^[Ա-֏]+\.\s+[^։]+[։]\s*", re.UNICODE)
# Also strip bare Armenian fast "Պահք։"
_HY_FAST_RE = re.compile(r"^\s*Պ[ա-ֆ]+[ք]?[։.]\s*", re.UNICODE)


def _clean_en(raw: str) -> str:
    """Extract meaningful English feast/saint name."""
    s = raw.strip()
    # Strip "Xth day of Y - " prefix
    s = _EN_PREFIX_RE.sub("", s)
    # Strip "Fast day - " prefix
    s = _FAST_PREFIX_RE.sub("", s)
    return s.strip()


def _clean_hy(raw: str) -> str | None:
    """Strip Armenian ordinal/fast prefix; return None if nothing remains."""
    if not raw:
        return None
    s = raw.strip().strip('"').strip()
    # Strip bare fast marker
    s = _HY_FAST_RE.sub("", s)
    # Strip ordinal prefix
    s = _HY_PREFIX_RE.sub("", s)
    s = s.strip().strip("։").strip()
    if len(s) < 3:
        return None
    return s if s else None


# ──────────────────────────────────────────────────────────
# Substantive entry filter
# ──────────────────────────────────────────────────────────

# Keywords that indicate substantive content (case-insensitive)
_KEYWORDS_RE = re.compile(
    r"\b(?:saint|saints|sts?\.?|st\.?|feast of|commemoration|discovery|birth of|"
    r"prophet|apostle|patriarch|forerunner|martyr|confessor|venerable|hermit|"
    r"bishop|deacon|priest|king|queen|prince|emperor|"
    r"theophany|presentation|assumption|ascension|pentecost|"
    r"transfiguration|resurrection|baptism|epiphany|holy cross|"
    r"vardavar|enkutatash|remembrance of the passion|last supper|"
    r"translators|illuminator|raising|dormition|exaltation|"
    r"children of bethlehem|magi|holy innocents)\b",
    re.IGNORECASE,
)
# ALL CAPS sequence (major feast like NATIVITY, RESURRECTION) — case-sensitive
_ALLCAPS_RE = re.compile(r"\b[A-Z]{3,}\b")

# Pure period-ordinal entries: "Nth day of X", "Nth Sunday of X", etc.
_ORDINAL_START_RE = re.compile(
    r"^(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty.?\w*|thirtieth|thirty.?\w*)"
    r"\s+(?:day of|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b",
    re.IGNORECASE,
)

_EXACT_NOISE_RE = re.compile(
    r"^(?:fast day|"
    r"great (?:monday|tuesday|wednesday|thursday|friday|saturday)|"
    r"eve of great lent|eve of the fast of catechumens?|"
    r"remembrance of the dead|"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth)\s+sunday (?:of|after|before) \w+)$",
    re.IGNORECASE,
)


def _has_content(text: str) -> bool:
    return bool(_KEYWORDS_RE.search(text) or _ALLCAPS_RE.search(text))


def _is_substantive(en_raw: str) -> bool:
    """True if this entry has meaningful saint/feast content worth keeping."""
    s = en_raw.strip()

    # Exact noise: bare fast day, weekday names, Sunday-of-period
    if _EXACT_NOISE_RE.match(s):
        return False

    # Ordinal-day-of-period: keep ONLY if there's a "- Saint/Feast..." after dash
    if _ORDINAL_START_RE.match(s):
        sep = re.split(r"\s*[-–]\s*", s, maxsplit=1)
        if len(sep) < 2:
            return False   # pure "Nth day of X" with no saint
        after = sep[1]
        return _has_content(after)

    return _has_content(s)


# ──────────────────────────────────────────────────────────
# Feast type detection
# ──────────────────────────────────────────────────────────

_FEAST_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bnew martyr\b", re.I), "New Martyr"),
    (re.compile(r"\bhieromartyr\b", re.I), "Hieromartyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"\bvenerable|hermit|abbot|abbess\b", re.I), "Venerable"),
    (re.compile(r"\bconfessor\b", re.I), "Confessor"),
    (re.compile(r"\bapostle\b", re.I), "Apostle"),
    (re.compile(r"\bforerunner|baptist\b", re.I), "Prophet"),
    (re.compile(r"\bprophet\b", re.I), "Prophet"),
    (re.compile(r"\bbishop|patriarch|metropolitan|archbishop|cathol?icos\b", re.I), "Hierarch"),
    (re.compile(r"\bking|queen|prince|emperor|princess\b", re.I), "Righteous"),
    (re.compile(r"\bnativity|theophany|presentation|assumption|ascension|pentecost|"
                r"transfiguration|resurrection|holy cross|discovery|vardavar\b", re.I), "Feast"),
]


def _feast_type(name: str) -> str:
    for pattern, ft in _FEAST_TYPE_RULES:
        if pattern.search(name):
            return ft
    return "Saint"


# ──────────────────────────────────────────────────────────
# Wikipedia enrichment
# ──────────────────────────────────────────────────────────

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_WEAK_WORDS = frozenset({
    "the", "of", "and", "his", "her", "our", "lord", "holy", "blessed",
    "saint", "saints", "feast", "commemoration", "day", "fast", "great",
    "church", "first", "second", "third",
})


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


def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_extracts(titles: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i: i + 50]
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
        for r in (data.get("query", {}).get("redirects", [])
                  + data.get("query", {}).get("normalized", [])):
            norm[r["from"]] = r["to"]

        for page in data.get("query", {}).get("pages", {}).values():
            desc = _extract_text(page)
            if not desc:
                continue
            title = page.get("title", "")
            wiki_url = ("https://en.wikipedia.org/wiki/"
                        + urllib.parse.quote(title.replace(" ", "_")))
            result[title] = {"description": desc, "url": wiki_url}

        for orig in batch:
            resolved = norm.get(orig, orig)
            if resolved in result and orig not in result:
                result[orig] = result[resolved]

        if i + 50 < len(titles):
            time.sleep(0.3)
    return result


def _candidate_titles(name: str) -> list[str]:
    """Extract Wikipedia article candidates from an English feast name."""
    # Strip prefix tokens
    cleaned = re.sub(
        r"^(?:saints?|sts?\.?|st\.?|feast of\s+(?:the\s+)?|commemoration of\s+(?:the\s+)?|"
        r"birth of\s+(?:the\s+)?|discovery of\s+(?:the\s+)?|"
        r"holy\s+|eve of\s+(?:the\s+)?|the\s+)",
        "", name, flags=re.IGNORECASE,
    ).strip()
    # Split multi-saint names on " and " / " & " / ","
    parts = re.split(r"\s*(?:,\s*|\s+and\s+|\s*&\s*)\s*", cleaned)
    titles = []
    for p in parts:
        p = p.strip().strip(".")
        if not p or len(p) < 4:
            continue
        words = p.split()
        # Filter generic words
        sig = [w for w in words if w.lower() not in _WEAK_WORDS]
        if sig:
            titles.append(p)
    return titles[:3]   # cap to avoid explosion


def enrich(entries: list[dict], delay: float = 0.3) -> dict[str, dict]:
    """Return {name: {description, url}} enrichment map."""
    all_titles: list[str] = []
    for e in entries:
        all_titles.extend(_candidate_titles(e["name"]))
    all_titles = list(dict.fromkeys(all_titles))  # dedup preserving order

    print(f"  Fetching {len(all_titles)} Wikipedia articles...", file=sys.stderr)
    result = fetch_extracts(all_titles)
    print(f"  Got {len(result)} descriptions", file=sys.stderr)
    return result


# ──────────────────────────────────────────────────────────
# Build output
# ──────────────────────────────────────────────────────────

def build_output(
    en_map: dict[str, str],
    hy_map: dict[str, str],
    enrichment: dict[str, dict],
) -> list[dict]:
    by_md: dict[str, list] = {}

    for md, en_raw in sorted(en_map.items()):
        if not _is_substantive(en_raw):
            continue

        name_en = _clean_en(en_raw)
        name_hy = _clean_hy(hy_map.get(md, ""))

        # Try to find enrichment
        enrich_data: dict = {}
        for cand in _candidate_titles(name_en):
            if cand in enrichment:
                enrich_data = enrichment[cand]
                break

        saint: dict = {
            "name": name_en,
            "name_hy": name_hy,
            "title": name_en,
            "feast_type": _feast_type(name_en),
            "hagiography_url": enrich_data.get("url") or None,
            "notes": enrich_data.get("description") or (
                "Armenian Apostolic Church commemoration."
            ),
            "canonized_by": "Armenian Apostolic Church",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        by_md.setdefault(md, []).append(saint)

    return [
        {"month_day": md, "tradition": "armenian", "calendar": "gregorian", "saints": saints}
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
                else:
                    # Update existing with Armenian name + enrichment if missing
                    for existing_saint in by_md[md]["saints"]:
                        if existing_saint["name"] == saint["name"]:
                            if not existing_saint.get("name_hy") and saint.get("name_hy"):
                                existing_saint["name_hy"] = saint["name_hy"]
                            if not existing_saint.get("hagiography_url") and saint.get("hagiography_url"):
                                existing_saint["hagiography_url"] = saint["hagiography_url"]
                            # Upgrade notes when existing is absent or is a default placeholder.
                            existing_note = existing_saint.get("notes") or ""
                            if saint.get("notes") and (
                                not existing_note
                                or existing_note.startswith("Armenian Apostolic Church commemoration")
                            ):
                                existing_saint["notes"] = saint["notes"]
    return [by_md[md] for md in sorted(by_md)]


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Armenian Apostolic Church calendar from dual ICS files"
    )
    parser.add_argument("--out", default="backend/app/data/traditions/armenian_saints.json")
    parser.add_argument("--merge", action="store_true",
                        help="Merge into existing file instead of replacing")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Skip Wikipedia enrichment")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching English ICS...", file=sys.stderr)
    en_ics = _fetch(ICS_EN)
    en_map = parse_ics(en_ics)
    print(f"  {len(en_map)} events", file=sys.stderr)

    print("Fetching Armenian ICS...", file=sys.stderr)
    hy_ics = _fetch(ICS_AM)
    hy_map = parse_ics(hy_ics)
    print(f"  {len(hy_map)} events", file=sys.stderr)

    # Count substantive entries
    substantive = [(md, s) for md, s in sorted(en_map.items()) if _is_substantive(s)]
    print(f"  {len(substantive)} substantive entries (after filtering noise)", file=sys.stderr)

    if args.dry_run:
        print("\nSample entries:", file=sys.stderr)
        for md, en_raw in substantive[:20]:
            name_en = _clean_en(en_raw)
            name_hy = _clean_hy(hy_map.get(md, ""))
            print(f"  {md}: {name_en[:60]}", file=sys.stderr)
            if name_hy:
                print(f"       {name_hy[:60]}", file=sys.stderr)
        print(f"\n  (dry-run — no file written)", file=sys.stderr)
        return

    enrichment: dict[str, dict] = {}
    if not args.no_enrich:
        entries_for_enrich = [
            {"name": _clean_en(s)} for _, s in substantive
        ]
        enrichment = enrich(entries_for_enrich)

    output = build_output(en_map, hy_map, enrichment)

    if args.merge and out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            existing = json.load(f)
        output = merge_outputs(existing, output)
        print(f"  Merged with {len(existing)} existing entries", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    enriched = sum(1 for e in output for s in e["saints"] if s.get("hagiography_url"))
    bilingual = sum(1 for e in output for s in e["saints"] if s.get("name_hy"))
    print(
        f"\nWrote {len(output)} entries ({total} saints, "
        f"{enriched} enriched, {bilingual} bilingual) → {out_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
