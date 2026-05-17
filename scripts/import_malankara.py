#!/usr/bin/env python3
"""
Import Malankara Orthodox Syrian Church calendar from multiple sources.

Sources:
  1. Malankara Google Calendar (ICS) — Gregorian dates, primary MOSC feasts
  2. Syriac Patriarchate ICS — shared saints (Julian civil → subtract 13 days)
  3. Panjangom PDF (mosc.in) — official MOSC almanac
  4. syriacorthodoxresources.org — shared Syriac saints (Julian → subtract 13 days)
  5. mosc-temp.com — additional MOSC feasts (Gregorian dates)
  6. Wikipedia enrichment

Usage:
    python3 scripts/import_malankara.py --dry-run
    python3 scripts/import_malankara.py --out backend/app/data/traditions/malankara_saints.json
    python3 scripts/import_malankara.py --no-pdf --no-syriac-web --no-mosc-web
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ── Source URLs ────────────────────────────────────────────────────────────────
_MALANKARA_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_e25347a722e88a9c41c803b417648ec62e259587b6af76f51c5a491a886fed49"
    "%40group.calendar.google.com/public/basic.ics"
)
_SYRIAC_ICS_URL = (
    "https://dss-syriacpatriarchate.org/wp-content/uploads/2025/12/"
    "Calender-of-Feast-2026.ics"
)
_PANJANGOM_PDF_URL = "https://mosc.in/uploads/2023/12/Panjangom_English_25_Online.pdf"
_SYRIAC_WEB_URL = "http://syriacorthodoxresources.org/Calendar/"
_MOSC_WEB_URL = "https://mosc-temp.com/mosc-redesign/the-church/church-calendar"
_WIKI_API = "https://en.wikipedia.org/w/api.php"

_JULIAN_OFFSET = 13  # days Julian calendar is behind Gregorian in 21st century

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0",
}

# ── ICS parsing ────────────────────────────────────────────────────────────────

_VEVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
_DTSTART_RE = re.compile(r"DTSTART[^:]*:(\d{8})")
_SUMMARY_RE = re.compile(r"SUMMARY:(.+?)(?:\r?\n(?!\s)|\r?\nEND)", re.DOTALL)


def parse_ics(content: str) -> dict[str, str]:
    """Return {MM-DD: summary} — first occurrence per date."""
    result: dict[str, str] = {}
    for m in _VEVENT_RE.finditer(content):
        block = m.group(1)
        dm = _DTSTART_RE.search(block)
        sm = _SUMMARY_RE.search(block)
        if not dm or not sm:
            continue
        raw = dm.group(1)  # YYYYMMDD
        md = f"{raw[4:6]}-{raw[6:8]}"
        # Unfold RFC 5545 line folding (CRLF + space/tab) — replace with single space
        summary = re.sub(r"\r?\n[ \t]", " ", sm.group(1))
        summary = re.sub(r"\s+", " ", summary).strip()
        if md not in result:
            result[md] = summary
    return result


def julian_civil_to_malankara(md: str) -> str:
    """Convert a Julian feast date (as Gregorian civil MM-DD) to Malankara Gregorian MM-DD.

    Syriac ICS files show Julian feast days using Gregorian civil dates (e.g. Christmas
    = Julian Dec 25 = Jan 7 Gregorian). The Malankara Church uses the true Gregorian
    calendar since 1953, so we subtract the Julian offset (13 days in 21st century).
    """
    month, day = int(md[:2]), int(md[3:])
    # Year 2000 is a leap year — handles Julian Feb 29 edge case safely
    ref = date(2000, month, day) - timedelta(days=_JULIAN_OFFSET)
    return f"{ref.month:02d}-{ref.day:02d}"


# ── Name cleaning ──────────────────────────────────────────────────────────────

_HONORIFIC_RE = re.compile(
    r"^(?:(?:saint|saints?|sts?\.?|st\.?|blessed|venerable|"
    r"our venerable|righteous|new martyr|new-martyr|great)\s+)+",
    re.IGNORECASE,
)
_EVENT_PREFIX_RE = re.compile(
    r"^(?:feast of(?: the)?|commemoration of(?: the)?|"
    r"repose of(?: the)?|translation of(?: the)?)\s+",
    re.IGNORECASE,
)


def clean_name(raw: str) -> str:
    s = raw.strip()
    s = _EVENT_PREFIX_RE.sub("", s)
    s = _HONORIFIC_RE.sub("", s)
    return s.strip()


# ── Noise filter ───────────────────────────────────────────────────────────────

_SUBSTANTIVE_RE = re.compile(
    r"\b(?:saint|saints|sts?\.?|feast|commemoration|nativity|resurrection|"
    r"ascension|pentecost|transfiguration|dormition|presentation|epiphany|"
    r"annunciation|holy cross|apostle|martyr|prophet|hierarch|venerable|"
    r"blessed|baptism|assumption|theophany|perunnal|thirunal)\b",
    re.IGNORECASE,
)
_ALLCAPS_RE = re.compile(r"\b[A-Z]{4,}\b")


def is_substantive(text: str) -> bool:
    return bool(_SUBSTANTIVE_RE.search(text) or _ALLCAPS_RE.search(text))


# ── Feast type detection ───────────────────────────────────────────────────────

_FEAST_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:hieromartyr|new martyr|new-martyr)\b", re.I), "Hieromartyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"\bvenerable|hermit|abbot|abbess\b", re.I), "Venerable"),
    (re.compile(r"\bconfessor\b", re.I), "Confessor"),
    (re.compile(r"\bapostle\b", re.I), "Apostle"),
    (re.compile(r"\bforerunner|baptist\b", re.I), "Prophet"),
    (re.compile(r"\bprophet\b", re.I), "Prophet"),
    (re.compile(r"\bbishop|patriarch|metropolitan|archbishop|catholicos\b", re.I), "Hierarch"),
    (re.compile(r"\bking|queen|prince|emperor\b", re.I), "Righteous"),
    (re.compile(
        r"\bnativity|theophany|presentation|dormition|ascension|pentecost|"
        r"transfiguration|resurrection|annunciation|holy cross|epiphany|"
        r"perunnal|thirunal\b", re.I), "Feast"),
]


def feast_type(name: str) -> str:
    for pattern, ft in _FEAST_RULES:
        if pattern.search(name):
            return ft
    return "Saint"


# ── Normalization for deduplication ───────────────────────────────────────────

_NORMALIZE_STRIP_RE = re.compile(r"[^a-z0-9]+")
_DROP_TOKENS = frozenset({
    "saint", "saints", "st", "sts", "venerable", "blessed", "holy",
    "martyr", "new", "the", "of", "and", "our", "lord",
})


def normalize_key(name: str) -> str:
    tokens = _NORMALIZE_STRIP_RE.sub(" ", name.lower()).split()
    return " ".join(t for t in tokens if t not in _DROP_TOKENS)


# ── Entry and saint builders ───────────────────────────────────────────────────

def make_saint(
    name: str,
    notes: str | None = None,
    hagiography_url: str | None = None,
) -> dict:
    return {
        "name": clean_name(name),
        "title": name,
        "feast_type": feast_type(name),
        "hagiography_url": hagiography_url,
        "notes": notes,
        "canonized_by": "Malankara Orthodox Syrian Church",
        "canonization_scope": "oriental",
        "year_canonized": None,
    }


def make_entry(md: str, saints: list[dict]) -> dict:
    return {
        "month_day": md,
        "tradition": "malankara",
        "calendar": "gregorian",
        "saints": saints,
    }


# ── Merge ──────────────────────────────────────────────────────────────────────

def _merge_saint(base: dict, overlay: dict) -> None:
    """Overlay non-empty fields into base without overwriting existing data."""
    for field in ("title", "feast_type", "hagiography_url", "notes",
                  "canonized_by", "canonization_scope", "year_canonized"):
        if overlay.get(field) is not None and base.get(field) is None:
            base[field] = overlay[field]


def merge_into(base: list[dict], new: list[dict]) -> list[dict]:
    """Merge new entries into base. Adds new dates/saints; enriches existing."""
    by_md: dict[str, dict] = {e["month_day"]: e for e in base}
    for entry in new:
        md = entry["month_day"]
        if md not in by_md:
            by_md[md] = entry
        else:
            existing_keys = {normalize_key(s["name"]) for s in by_md[md]["saints"]}
            for saint in entry["saints"]:
                key = normalize_key(saint["name"])
                if key not in existing_keys:
                    by_md[md]["saints"].append(saint)
                    existing_keys.add(key)
                else:
                    for s in by_md[md]["saints"]:
                        if normalize_key(s["name"]) == key:
                            _merge_saint(s, saint)
                            break
    return sorted(by_md.values(), key=lambda e: e["month_day"])


# ── Output writer ──────────────────────────────────────────────────────────────

def write_output(entries: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    total = sum(len(e["saints"]) for e in entries)
    enriched = sum(1 for e in entries for s in e["saints"] if s.get("hagiography_url"))
    print(
        f"Wrote {len(entries)} entries ({total} saints, {enriched} enriched) → {path}",
        file=sys.stderr,
    )


# ── HTTP fetch ─────────────────────────────────────────────────────────────────

def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# ── Phase 1: Malankara Google Calendar ICS ────────────────────────────────────

def phase_malankara_ics() -> list[dict]:
    """Fetch Malankara public Google Calendar ICS — Gregorian dates, use as-is."""
    print("Phase 1: Malankara ICS...", file=sys.stderr)
    try:
        content = _fetch(_MALANKARA_ICS_URL)
    except Exception as exc:
        print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
        return []

    events = parse_ics(content)
    print(f"  {len(events)} raw events", file=sys.stderr)

    entries: list[dict] = []
    for md, summary in sorted(events.items()):
        if not is_substantive(summary):
            continue
        entries.append(make_entry(md, [make_saint(summary)]))

    print(f"  {len(entries)} substantive entries", file=sys.stderr)
    return entries


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Import Malankara Orthodox Syrian Church calendar"
    )
    p.add_argument(
        "--out",
        default="backend/app/data/traditions/malankara_saints.json",
    )
    p.add_argument("--no-ics",        action="store_true", help="Skip Malankara ICS")
    p.add_argument("--no-syriac-ics", action="store_true", help="Skip Syriac ICS")
    p.add_argument("--no-pdf",        action="store_true", help="Skip Panjangom PDF")
    p.add_argument("--no-syriac-web", action="store_true", help="Skip syriacorthodoxresources.org")
    p.add_argument("--no-mosc-web",   action="store_true", help="Skip mosc-temp.com")
    p.add_argument("--no-enrich",     action="store_true", help="Skip Wikipedia enrichment")
    p.add_argument("--dry-run",       action="store_true", help="Print summary, write nothing")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    out_path = Path(args.out)

    entries: list[dict] = []

    if not args.no_ics:
        entries = merge_into(entries, phase_malankara_ics())

    # Remaining phases added in later tasks:
    # syriac_ics, pdf, syriac_web, mosc_web, enrich

    print(f"\nTotal: {len(entries)} entries, "
          f"{sum(len(e['saints']) for e in entries)} saints", file=sys.stderr)

    if args.dry_run:
        print("\nSample (first 5):", file=sys.stderr)
        for e in entries[:5]:
            print(f"  {e['month_day']}: {e['saints'][0]['name'][:60]}", file=sys.stderr)
        print("(dry-run — nothing written)", file=sys.stderr)
        return

    write_output(entries, out_path)


if __name__ == "__main__":
    main()
