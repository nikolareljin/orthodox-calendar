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
import tempfile
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


# ── Phase 2: Syriac Patriarchate ICS ─────────────────────────────────────────

def phase_syriac_ics() -> list[dict]:
    """Fetch Syriac Patriarchate ICS — Julian feast dates shown as Gregorian civil dates.

    The Syriac Orthodox Church follows the Julian calendar, so their ICS dates are
    Gregorian civil equivalents of Julian feasts (e.g. Christmas = Jan 7, not Dec 25).
    Malankara uses the true Gregorian calendar (since 1953), so we subtract 13 days.
    """
    print("Phase 2: Syriac Patriarchate ICS...", file=sys.stderr)
    try:
        content = _fetch(_SYRIAC_ICS_URL)
    except Exception as exc:
        print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
        return []

    events = parse_ics(content)
    print(f"  {len(events)} raw events", file=sys.stderr)

    entries: list[dict] = []
    for syriac_md, summary in sorted(events.items()):
        if not is_substantive(summary):
            continue
        try:
            malankara_md = julian_civil_to_malankara(syriac_md)
        except (ValueError, IndexError):
            print(f"  WARN: skipping malformed date key {syriac_md!r}", file=sys.stderr)
            continue
        entries.append(make_entry(malankara_md, [make_saint(summary)]))

    print(f"  {len(entries)} substantive entries (after date conversion)", file=sys.stderr)
    return entries


# ── Phase 3: Panjangom PDF ────────────────────────────────────────────────────

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Matches: "January 7 - Feast of the Nativity" or "January 7: ..." or "January 7 ..."
_PDF_DATE_LINE_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<day>\d{1,2})"
    r"(?:[:\t \-–]+)(?P<rest>[^\n]+)",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        print(
            "  WARN: pdfplumber not installed. Run: pip install pdfplumber",
            file=sys.stderr,
        )
        return ""

    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
    except Exception as exc:
        print(f"  WARN: pdfplumber failed to read PDF: {exc}", file=sys.stderr)
        return ""
    return "\n".join(pages)


def phase_pdf(tmp_dir: Path) -> list[dict]:
    """Download and parse the official Panjangom (MOSC almanac) PDF."""
    print("Phase 3: Panjangom PDF...", file=sys.stderr)
    pdf_path = tmp_dir / "panjangom.pdf"

    if not pdf_path.exists():
        tmp_path = pdf_path.with_suffix(".pdf.tmp")
        try:
            print("  Downloading PDF...", file=sys.stderr)
            tmp_path.write_bytes(_fetch_bytes(_PANJANGOM_PDF_URL))
            tmp_path.rename(pdf_path)
            print(f"  Downloaded {pdf_path.stat().st_size // 1024} KB", file=sys.stderr)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            print(f"  WARN: PDF download failed: {exc}", file=sys.stderr)
            return []

    text = _extract_pdf_text(pdf_path)
    if not text:
        print("  WARN: no text extracted from PDF", file=sys.stderr)
        return []

    print(f"  Extracted {len(text)} chars of text", file=sys.stderr)

    entries: list[dict] = []
    seen: set[str] = set()
    for m in _PDF_DATE_LINE_RE.finditer(text):
        month_num = _MONTH_NAMES[m.group("month").lower()]
        day = int(m.group("day"))
        if day > 31:
            continue
        rest = m.group("rest").strip()
        if not is_substantive(rest):
            continue
        md = f"{month_num:02d}-{day:02d}"
        key = f"{md}:{normalize_key(clean_name(rest))}"
        if key in seen:
            continue
        seen.add(key)
        entries.append(make_entry(md, [make_saint(rest)]))

    print(f"  {len(entries)} substantive entries from PDF", file=sys.stderr)

    if not entries:
        print(
            "  WARN: 0 entries parsed. The PDF layout may differ from expected.\n"
            "  Inspect the PDF structure and adjust _PDF_DATE_LINE_RE if needed.",
            file=sys.stderr,
        )

    return entries


# ── Phase 4: syriacorthodoxresources.org ──────────────────────────────────────

_SYRIAC_WEB_DATE_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<day>\d{1,2})",
    re.IGNORECASE,
)


def _parse_bs4(
    html: str,
    date_re: re.Pattern,
) -> list[tuple[str, str]]:
    """Parse date-saint pairs from an HTML calendar page.

    Tries two strategies:
    1. Table rows with 2+ cells (date | saint)
    2. Heading elements followed by sibling list items / paragraphs
    Returns list of (MM-DD, saint_name) tuples.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  WARN: beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml",
              file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    pairs: list[tuple[str, str]] = []

    # Strategy 1: table rows with 2+ cells
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            date_text = cells[0].get_text(" ", strip=True)
            saint_text = cells[1].get_text(" ", strip=True)
            dm = date_re.search(date_text)
            if dm and is_substantive(saint_text):
                month = _MONTH_NAMES[dm.group("month").lower()]
                day = int(dm.group("day"))
                pairs.append((f"{month:02d}-{day:02d}", saint_text))

    # Strategy 2: heading + following siblings (list items / paragraphs)
    if not pairs:
        for heading in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
            dm = date_re.search(heading.get_text())
            if not dm:
                continue
            month = _MONTH_NAMES[dm.group("month").lower()]
            day = int(dm.group("day"))
            md = f"{month:02d}-{day:02d}"
            for sib in heading.next_siblings:
                if hasattr(sib, "name") and sib.name in ("h2", "h3", "h4", "strong", "b"):
                    break
                text = (sib.get_text(" ", strip=True)
                        if hasattr(sib, "get_text") else str(sib).strip())
                if text and is_substantive(text):
                    pairs.append((md, text))

    return pairs


def phase_syriac_web() -> list[dict]:
    """Scrape syriacorthodoxresources.org — shared Syriac/Malankara saints.

    Dates on this site are Julian (Syriac Orthodox follows Julian calendar).
    Apply the same 13-day conversion as the Syriac ICS phase.
    """
    print("Phase 4: syriacorthodoxresources.org...", file=sys.stderr)
    try:
        html = _fetch(_SYRIAC_WEB_URL)
    except Exception as exc:
        print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
        return []

    pairs = _parse_bs4(html, _SYRIAC_WEB_DATE_RE)
    print(f"  {len(pairs)} raw pairs found", file=sys.stderr)

    entries: list[dict] = []
    for julian_md, name in pairs:
        try:
            malankara_md = julian_civil_to_malankara(julian_md)
        except (ValueError, IndexError):
            print(f"  WARN: skipping malformed date {julian_md!r}", file=sys.stderr)
            continue
        entries.append(make_entry(malankara_md, [make_saint(name)]))

    print(f"  {len(entries)} entries after date conversion", file=sys.stderr)

    if not entries:
        print(
            "  WARN: 0 entries. The page layout may differ from expected strategies.",
            file=sys.stderr,
        )

    return entries


# ── Phase 5: mosc-temp.com ────────────────────────────────────────────────────

_MOSC_DATE_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<day>\d{1,2})",
    re.IGNORECASE,
)


def phase_mosc_web() -> list[dict]:
    """Scrape mosc-temp.com church calendar — Gregorian dates, use as-is."""
    print("Phase 5: mosc-temp.com...", file=sys.stderr)
    try:
        html = _fetch(_MOSC_WEB_URL)
    except Exception as exc:
        print(f"  WARN: fetch failed: {exc}", file=sys.stderr)
        return []

    pairs = _parse_bs4(html, _MOSC_DATE_RE)
    print(f"  {len(pairs)} raw pairs found", file=sys.stderr)

    entries: list[dict] = []
    for md, name in pairs:
        entries.append(make_entry(md, [make_saint(name)]))

    print(f"  {len(entries)} entries", file=sys.stderr)
    return entries


# ── Wikipedia enrichment ───────────────────────────────────────────────────────

_WEAK_WORDS = frozenset({
    "the", "of", "and", "his", "her", "our", "lord", "holy", "blessed",
    "saint", "saints", "feast", "commemoration", "day", "fast", "great",
    "church", "first", "second", "third",
})


def _candidate_titles(name: str) -> list[str]:
    cleaned = re.sub(
        r"^(?:saints?|sts?\.?|feast of\s+(?:the\s+)?|commemoration of\s+(?:the\s+)?|"
        r"holy\s+|the\s+)",
        "", name, flags=re.IGNORECASE,
    ).strip()
    parts = re.split(r"\s*(?:,\s*|\s+and\s+|\s*&\s*)\s*", cleaned)
    titles = []
    for p in parts:
        p = p.strip().strip(".")
        if not p or len(p) < 4:
            continue
        words = p.split()
        if [w for w in words if w.lower() not in _WEAK_WORDS]:
            titles.append(p)
    return titles[:3]


def _fetch_wiki_extracts(titles: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i: i + 50]
        try:
            params = urllib.parse.urlencode({
                "action": "query",
                "titles": "|".join(batch),
                "prop": "extracts",
                "exintro": "1",
                "exsentences": "3",
                "explaintext": "1",
                "redirects": "1",
                "format": "json",
            })
            url = f"{_WIKI_API}?{params}"
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except Exception as exc:
            print(f"  WARN: Wikipedia batch {i//50+1} failed: {exc}", file=sys.stderr)
            continue

        norm: dict[str, str] = {}
        for redir in (data.get("query", {}).get("redirects", [])
                      + data.get("query", {}).get("normalized", [])):
            norm[redir["from"]] = redir["to"]

        for page in data.get("query", {}).get("pages", {}).values():
            raw = (page.get("extract") or "").strip()
            if len(raw) < 30 or "may refer to:" in raw or "disambiguation" in raw.lower():
                continue
            title = page.get("title", "")
            wiki_url = ("https://en.wikipedia.org/wiki/"
                        + urllib.parse.quote(title.replace(" ", "_")))
            result[title] = {
                "description": " ".join(re.split(r"(?<=[.!?])\s+", raw)[:3])[:400],
                "url": wiki_url,
            }

        for orig in batch:
            key, seen = orig, set()
            while key in norm and key not in seen:
                seen.add(key)
                key = norm[key]
            if key in result and orig not in result:
                result[orig] = result[key]

        if i + 50 < len(titles):
            time.sleep(0.3)

    return result


def phase_enrich(entries: list[dict]) -> None:
    """Enrich saints in-place with Wikipedia hagiography_url and notes."""
    all_names: list[str] = []
    for entry in entries:
        for saint in entry["saints"]:
            if not saint.get("hagiography_url"):
                all_names.extend(_candidate_titles(saint["name"]))
    all_names = list(dict.fromkeys(all_names))  # dedup, preserve order

    print(f"Phase 6: Wikipedia enrichment ({len(all_names)} candidates)...", file=sys.stderr)
    wiki = _fetch_wiki_extracts(all_names)
    print(f"  Got {len(wiki)} descriptions", file=sys.stderr)

    for entry in entries:
        for saint in entry["saints"]:
            if saint.get("hagiography_url"):
                continue
            for cand in _candidate_titles(saint["name"]):
                if cand in wiki:
                    saint["hagiography_url"] = wiki[cand]["url"]
                    if not saint.get("notes"):
                        saint["notes"] = wiki[cand]["description"]
                    break


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

    if not args.no_syriac_ics:
        entries = merge_into(entries, phase_syriac_ics())

    if not args.no_pdf:
        tmp = Path(tempfile.gettempdir()) / "malankara_import"
        tmp.mkdir(exist_ok=True)
        entries = merge_into(entries, phase_pdf(tmp))

    if not args.no_syriac_web:
        entries = merge_into(entries, phase_syriac_web())

    if not args.no_mosc_web:
        entries = merge_into(entries, phase_mosc_web())

    if not args.no_enrich:
        phase_enrich(entries)

    print(f"\nTotal: {len(entries)} entries, "
          f"{sum(len(e['saints']) for e in entries)} saints", file=sys.stderr)

    if args.dry_run:
        print("\nSample (first 5):", file=sys.stderr)
        for e in entries[:5]:
            saint_name = e["saints"][0]["name"][:60] if e["saints"] else "(no saints)"
            print(f"  {e['month_day']}: {saint_name}", file=sys.stderr)
        print("(dry-run — nothing written)", file=sys.stderr)
        return

    write_output(entries, out_path)


if __name__ == "__main__":
    main()
