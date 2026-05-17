# Malankara Orthodox Calendar Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/import_malankara.py`, a multi-source importer that produces `backend/app/data/traditions/malankara_saints.json`, and update `config.py` so the Malankara tradition uses `CalendarSystem.GREGORIAN` (MOSC adopted the Gregorian calendar in 1953).

**Architecture:** Six sequential, independently skippable phases — Malankara Google Calendar ICS (base layer) → Syriac Patriarchate ICS (Julian→Gregorian conversion) → Panjangom PDF → Syriac web calendar → MOSC web calendar → Wikipedia enrichment — merged into a single output JSON. Core parsing utilities are unit-tested; network phases are validated via `--dry-run`.

**Tech Stack:** Python stdlib (`urllib.request`, `re`, `json`, `argparse`), `pdfplumber` (PDF extraction), `beautifulsoup4` + `lxml` (HTML), Wikipedia API, `pytest` (tests).

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/config.py` | Modify | Change malankara to `GREGORIAN`, remove `data_key` |
| `scripts/requirements-import.txt` | Create | Import-only deps (not in production server) |
| `scripts/import_malankara.py` | Create | All six phases + merge + output |
| `scripts/tests/test_import_malankara.py` | Create | Unit tests for pure utility functions |
| `backend/app/data/traditions/malankara_saints.json` | Generate | Final output (committed after successful run) |

---

## Task 1: Update config.py and create import dependency file

**Files:**
- Modify: `backend/app/config.py`
- Create: `scripts/requirements-import.txt`

- [ ] **Step 1: Update malankara entry in config.py**

In `backend/app/config.py`, replace the `malankara` entry:

```python
# Before:
"malankara": Tradition(
    name="Malankara Orthodox Syrian Church",
    calendar=CalendarSystem.JULIAN,
    aliases=["mosc", "indian-orthodox", "thomas-christians"],
    data_key="oriental",   # shares Oriental Orthodox sanctoral data until Malankara-specific set is built
),

# After:
"malankara": Tradition(
    name="Malankara Orthodox Syrian Church",
    calendar=CalendarSystem.GREGORIAN,
    aliases=["mosc", "indian-orthodox", "thomas-christians"],
),
```

- [ ] **Step 2: Create scripts/requirements-import.txt**

```
pdfplumber>=0.11.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

- [ ] **Step 3: Install import dependencies**

Run from the project root (activate whatever virtualenv you use, or use system Python):

```bash
pip install -r scripts/requirements-import.txt
```

Expected: installs `pdfplumber`, `beautifulsoup4`, `lxml` without errors.

- [ ] **Step 4: Run backend smoke test to verify config change doesn't break anything**

```bash
cd backend
python -m pytest tests/test_api_smoke.py -v
```

Expected: all tests pass. Malankara will return empty saints (no dataset yet) — that's correct.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py scripts/requirements-import.txt
git commit -m "feat: switch malankara to Gregorian calendar, add import deps"
```

---

## Task 2: Script skeleton + ICS parsing utilities

**Files:**
- Create: `scripts/import_malankara.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/test_import_malankara.py`

- [ ] **Step 1: Write failing tests for ICS parser and date converter**

Create `scripts/tests/__init__.py` (empty):
```python
```

Create `scripts/tests/test_import_malankara.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from import_malankara import parse_ics, julian_civil_to_malankara


def test_parse_ics_basic():
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20260107\r\n"
        "SUMMARY:Feast of the Nativity of Our Lord\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert result == {"01-07": "Feast of the Nativity of Our Lord"}


def test_parse_ics_keeps_first_occurrence():
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20260107\r\nSUMMARY:First\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20260107\r\nSUMMARY:Second\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert result["01-07"] == "First"


def test_parse_ics_multiline_summary():
    # RFC 5545: long lines are folded with CRLF + space
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20260301\r\n"
        "SUMMARY:Feast of Saint\r\n Thomas the Apostle\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert "03-01" in result


def test_julian_civil_to_malankara_christmas():
    # Julian Dec 25 → Syriac ICS shows Jan 7 (Gregorian civil) → Malankara Dec 25
    assert julian_civil_to_malankara("01-07") == "12-25"


def test_julian_civil_to_malankara_new_year():
    # Julian Jan 1 → Syriac ICS shows Jan 14 → Malankara Jan 1
    assert julian_civil_to_malankara("01-14") == "01-01"


def test_julian_civil_to_malankara_offset():
    # Verify consistent 13-day offset across months
    assert julian_civil_to_malankara("03-13") == "02-28"
    assert julian_civil_to_malankara("04-14") == "04-01"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd scripts
python -m pytest tests/test_import_malankara.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'import_malankara'`

- [ ] **Step 3: Create scripts/import_malankara.py with ICS utilities**

```python
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
        # Unfold RFC 5545 line folding (CRLF + space/tab)
        summary = re.sub(r"\r?\n[ \t]", "", sm.group(1))
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
```

- [ ] **Step 4: Run tests again**

```bash
cd scripts
python -m pytest tests/test_import_malankara.py::test_parse_ics_basic \
    tests/test_import_malankara.py::test_julian_civil_to_malankara_christmas -v
```

Expected: both PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/test_import_malankara.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ..  # back to project root
git add scripts/import_malankara.py scripts/tests/__init__.py \
    scripts/tests/test_import_malankara.py
git commit -m "feat: malankara importer skeleton with ICS parsing utilities"
```

---

## Task 3: Name cleaning, noise filter, feast type, and normalization

**Files:**
- Modify: `scripts/import_malankara.py` (append after ICS section)
- Modify: `scripts/tests/test_import_malankara.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_import_malankara.py`:

```python
from import_malankara import clean_name, is_substantive, feast_type, normalize_key


def test_clean_name_strips_saint_prefix():
    assert clean_name("Saint Thomas the Apostle") == "Thomas the Apostle"
    assert clean_name("Saints Peter and Paul") == "Peter and Paul"
    assert clean_name("St. Mary the Virgin") == "Mary the Virgin"


def test_clean_name_strips_event_prefix():
    assert clean_name("Feast of the Nativity") == "Nativity"
    assert clean_name("Commemoration of the Holy Martyrs") == "Holy Martyrs"


def test_is_substantive_keeps_saints_and_feasts():
    assert is_substantive("Feast of Saint Thomas the Apostle")
    assert is_substantive("Commemoration of the Holy Martyrs")
    assert is_substantive("NATIVITY OF OUR LORD")
    assert is_substantive("Perunnal of Saint Mary")
    assert is_substantive("Thirunal of the Apostle")


def test_is_substantive_drops_noise():
    assert not is_substantive("Fast day")
    assert not is_substantive("Lenten weekday")
    assert not is_substantive("")
    assert not is_substantive("Sunday of the Great Lent")


def test_feast_type_detection():
    assert feast_type("Saint Thomas the Martyr") == "Martyr"
    assert feast_type("Hieromartyr Ignatius") == "Hieromartyr"
    assert feast_type("Venerable Ephrem the Syrian") == "Venerable"
    assert feast_type("Feast of the Nativity") == "Feast"
    assert feast_type("Perunnal of Our Lady") == "Feast"
    assert feast_type("Thirunal of the church") == "Feast"
    assert feast_type("Apostle Thomas") == "Apostle"
    assert feast_type("Prophet Elijah") == "Prophet"
    assert feast_type("Some unknown celebration") == "Saint"


def test_normalize_key_deduplicates_same_saint():
    assert normalize_key("Saint Thomas") == normalize_key("Thomas")
    assert normalize_key("St. Mary") == normalize_key("Mary")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd scripts
python -m pytest tests/test_import_malankara.py -v 2>&1 | grep FAILED
```

Expected: new tests fail with `ImportError`.

- [ ] **Step 3: Implement name cleaning, noise filter, feast type, normalization**

Append to `scripts/import_malankara.py` after the ICS parsing section:

```python
# ── Name cleaning ──────────────────────────────────────────────────────────────

_HONORIFIC_RE = re.compile(
    r"^(?:(?:saint|saints?|sts?\.?|st\.?|holy|blessed|venerable|"
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
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/test_import_malankara.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add scripts/import_malankara.py scripts/tests/test_import_malankara.py
git commit -m "feat: name cleaning, noise filter, feast type, normalization utilities"
```

---

## Task 4: Merge logic, entry builder, output writer

**Files:**
- Modify: `scripts/import_malankara.py`
- Modify: `scripts/tests/test_import_malankara.py`

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_import_malankara.py`:

```python
from import_malankara import make_saint, make_entry, merge_into


def _s(name, url=None, notes=None):
    return {
        "name": name, "title": name, "feast_type": "Saint",
        "hagiography_url": url, "notes": notes,
        "canonized_by": "Malankara Orthodox Syrian Church",
        "canonization_scope": "oriental", "year_canonized": None,
    }


def test_merge_into_adds_new_date():
    base = [make_entry("01-07", [_s("Nativity")])]
    new  = [make_entry("01-14", [_s("New Year")])]
    result = merge_into(base, new)
    assert len(result) == 2
    assert result[0]["month_day"] == "01-07"
    assert result[1]["month_day"] == "01-14"


def test_merge_into_deduplicates_same_saint():
    base = [make_entry("07-03", [_s("Thomas")])]
    dupe = [make_entry("07-03", [_s("Saint Thomas")])]
    result = merge_into(base, dupe)
    assert len(result[0]["saints"]) == 1


def test_merge_into_enriches_existing():
    base = [make_entry("07-03", [_s("Thomas", url=None, notes=None)])]
    rich = [make_entry("07-03", [_s("Thomas", url="https://en.wikipedia.org/wiki/Thomas")])]
    result = merge_into(base, rich)
    assert result[0]["saints"][0]["hagiography_url"] == "https://en.wikipedia.org/wiki/Thomas"


def test_merge_into_adds_new_saint_same_date():
    base = [make_entry("07-03", [_s("Thomas")])]
    new  = [make_entry("07-03", [_s("Mary Magdalene")])]
    result = merge_into(base, new)
    assert len(result[0]["saints"]) == 2


def test_make_saint_sets_required_fields():
    s = make_saint("Nativity of Our Lord")
    assert s["name"] == "Nativity of Our Lord"
    assert s["feast_type"] == "Feast"
    assert s["canonized_by"] == "Malankara Orthodox Syrian Church"
    assert s["canonization_scope"] == "oriental"


def test_make_entry_structure():
    e = make_entry("12-25", [make_saint("Nativity")])
    assert e["tradition"] == "malankara"
    assert e["calendar"] == "gregorian"
    assert e["month_day"] == "12-25"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd scripts
python -m pytest tests/test_import_malankara.py -v 2>&1 | grep FAILED | head -5
```

Expected: new tests fail with `ImportError`.

- [ ] **Step 3: Implement merge logic, entry/saint builders, output writer**

Append to `scripts/import_malankara.py`:

```python
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
        if overlay.get(field) and not base.get(field):
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
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/test_import_malankara.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add scripts/import_malankara.py scripts/tests/test_import_malankara.py
git commit -m "feat: merge logic, entry builders, output writer"
```

---

## Task 5: Malankara ICS phase (primary source)

**Files:**
- Modify: `scripts/import_malankara.py`

- [ ] **Step 1: Implement HTTP fetch helper and Malankara ICS phase**

Append to `scripts/import_malankara.py`:

```python
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
```

- [ ] **Step 2: Add argparse and dry-run wiring (partial main)**

Append to `scripts/import_malankara.py`:

```python
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
```

- [ ] **Step 3: Dry-run with only Malankara ICS**

```bash
python3 scripts/import_malankara.py \
    --no-syriac-ics --no-pdf --no-syriac-web --no-mosc-web --no-enrich \
    --dry-run
```

Expected: prints count of events fetched from Google Calendar ICS and 5 sample entries. If the calendar is private or empty, you'll see `WARN: fetch failed` — that's handled gracefully.

- [ ] **Step 4: Commit**

```bash
git add scripts/import_malankara.py
git commit -m "feat: malankara ICS phase + CLI skeleton"
```

---

## Task 6: Syriac Patriarchate ICS phase (Julian→Gregorian conversion)

**Files:**
- Modify: `scripts/import_malankara.py`

- [ ] **Step 1: Implement Syriac ICS phase**

Append the following after `phase_malankara_ics()` in `scripts/import_malankara.py`:

```python
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
        malankara_md = julian_civil_to_malankara(syriac_md)
        entries.append(make_entry(malankara_md, [make_saint(summary)]))

    print(f"  {len(entries)} substantive entries (after date conversion)", file=sys.stderr)
    return entries
```

- [ ] **Step 2: Wire into main()**

In `main()`, add after the Malankara ICS block:

```python
    if not args.no_syriac_ics:
        entries = merge_into(entries, phase_syriac_ics())
```

- [ ] **Step 3: Dry-run with both ICS sources**

```bash
python3 scripts/import_malankara.py \
    --no-pdf --no-syriac-web --no-mosc-web --no-enrich \
    --dry-run
```

Expected: combined count from both ICS sources. Verify that "12-25" appears (Christmas = Julian Dec 25 → Malankara Dec 25), not "01-07".

- [ ] **Step 4: Commit**

```bash
git add scripts/import_malankara.py
git commit -m "feat: syriac ICS phase with Julian-to-Gregorian date conversion"
```

---

## Task 7: Panjangom PDF phase

**Files:**
- Modify: `scripts/import_malankara.py`

- [ ] **Step 1: Implement PDF phase**

Append after `phase_syriac_ics()`:

```python
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
    r"(?:[:\s\-–]+)(?P<rest>[^\n]+)",
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
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n".join(pages)


def phase_pdf(tmp_dir: Path) -> list[dict]:
    """Download and parse the official Panjangom (MOSC almanac) PDF."""
    print("Phase 3: Panjangom PDF...", file=sys.stderr)
    pdf_path = tmp_dir / "panjangom.pdf"

    if not pdf_path.exists():
        try:
            print(f"  Downloading PDF...", file=sys.stderr)
            pdf_path.write_bytes(_fetch_bytes(_PANJANGOM_PDF_URL))
            print(f"  Downloaded {pdf_path.stat().st_size // 1024} KB", file=sys.stderr)
        except Exception as exc:
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
        key = f"{md}:{normalize_key(rest)}"
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
```

- [ ] **Step 2: Wire into main()**

Add `import tempfile` at the top of the file (after existing imports). Then in `main()`, add before the final print:

```python
    if not args.no_pdf:
        tmp = Path(tempfile.gettempdir()) / "malankara_import"
        tmp.mkdir(exist_ok=True)
        entries = merge_into(entries, phase_pdf(tmp))
```

Also add `import tempfile` at the top of the script.

- [ ] **Step 3: Dry-run PDF phase**

```bash
python3 scripts/import_malankara.py \
    --no-syriac-ics --no-syriac-web --no-mosc-web --no-enrich \
    --dry-run
```

Expected: PDF downloads to temp dir and prints parsed count. If count is 0 and a warning appears, inspect the extracted text:

```bash
python3 -c "
import pdfplumber, sys
with pdfplumber.open('/tmp/malankara_import/panjangom.pdf') as pdf:
    for i, page in enumerate(pdf.pages[:3]):
        print(f'--- Page {i+1} ---')
        print(page.extract_text()[:500])
"
```

Adjust `_PDF_DATE_LINE_RE` if the date format differs from expected.

- [ ] **Step 4: Commit**

```bash
git add scripts/import_malankara.py
git commit -m "feat: Panjangom PDF phase with pdfplumber extraction"
```

---

## Task 8: Web scraping phases (Syriac resources + MOSC site)

**Files:**
- Modify: `scripts/import_malankara.py`

- [ ] **Step 1: Implement Syriac web phase**

Append after `phase_pdf()`:

```python
# ── Phase 4: syriacorthodoxresources.org ──────────────────────────────────────

_SYRIAC_WEB_DATE_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?P<day>\d{1,2})",
    re.IGNORECASE,
)


def _parse_bs4(html: str, base_url: str) -> list[dict]:
    """Parse date-saint pairs from BeautifulSoup. Handles common calendar page layouts:
    table rows (date | saint), lists with date headers, or paragraphs.
    Returns list of (julian_civil_md, saint_name) tuples.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  WARN: beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml",
              file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "lxml")

    # Remove nav/footer/header noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    pairs: list[tuple[str, str]] = []

    # Strategy 1: table rows with 2+ cells
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            date_text = cells[0].get_text(" ", strip=True)
            saint_text = cells[1].get_text(" ", strip=True)
            dm = _SYRIAC_WEB_DATE_RE.search(date_text)
            if dm and is_substantive(saint_text):
                month = _MONTH_NAMES[dm.group("month").lower()]
                day = int(dm.group("day"))
                pairs.append((f"{month:02d}-{day:02d}", saint_text))

    # Strategy 2: heading + following list items
    if not pairs:
        for heading in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
            dm = _SYRIAC_WEB_DATE_RE.search(heading.get_text())
            if not dm:
                continue
            month = _MONTH_NAMES[dm.group("month").lower()]
            day = int(dm.group("day"))
            md = f"{month:02d}-{day:02d}"
            # Gather text from siblings until next heading
            for sib in heading.next_siblings:
                if hasattr(sib, "name") and sib.name in ("h2", "h3", "h4"):
                    break
                text = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
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

    pairs = _parse_bs4(html, _SYRIAC_WEB_URL)
    print(f"  {len(pairs)} raw pairs found", file=sys.stderr)

    entries: list[dict] = []
    for julian_md, name in pairs:
        malankara_md = julian_civil_to_malankara(julian_md)
        entries.append(make_entry(malankara_md, [make_saint(name)]))

    print(f"  {len(entries)} entries after date conversion", file=sys.stderr)

    if not entries:
        print(
            "  WARN: 0 entries. The page layout may differ from expected strategies.\n"
            "  Fetch and inspect: python3 -c \"import urllib.request; "
            "print(urllib.request.urlopen('" + _SYRIAC_WEB_URL + "').read()[:2000].decode())\"",
            file=sys.stderr,
        )

    return entries
```

- [ ] **Step 2: Implement MOSC web phase**

Append after `phase_syriac_web()`:

```python
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

    # Reuse _parse_bs4 — site uses Gregorian dates so no conversion needed
    pairs = _parse_bs4(html, _MOSC_WEB_URL)
    print(f"  {len(pairs)} raw pairs found", file=sys.stderr)

    entries: list[dict] = []
    for md, name in pairs:
        entries.append(make_entry(md, [make_saint(name)]))

    print(f"  {len(entries)} entries", file=sys.stderr)
    return entries
```

- [ ] **Step 3: Wire both web phases into main()**

In `main()`, add after the PDF block:

```python
    if not args.no_syriac_web:
        entries = merge_into(entries, phase_syriac_web())

    if not args.no_mosc_web:
        entries = merge_into(entries, phase_mosc_web())
```

- [ ] **Step 4: Dry-run all non-enrich phases**

```bash
python3 scripts/import_malankara.py --no-enrich --dry-run
```

Expected: runs all 5 data phases, prints total count. If a web phase returns 0 entries, inspect the raw HTML:

```bash
python3 -c "
import urllib.request
html = urllib.request.urlopen('http://syriacorthodoxresources.org/Calendar/').read().decode()
print(html[:3000])
"
```

Adapt `_parse_bs4` strategies if neither table-row nor heading-list approach finds entries.

- [ ] **Step 5: Commit**

```bash
git add scripts/import_malankara.py
git commit -m "feat: syriac web and MOSC web scraping phases"
```

---

## Task 9: Wikipedia enrichment

**Files:**
- Modify: `scripts/import_malankara.py`

- [ ] **Step 1: Implement Wikipedia enrichment (ported from Armenian importer)**

Append after `phase_mosc_web()`:

```python
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
            resolved = norm.get(orig, orig)
            if resolved in result and orig not in result:
                result[orig] = result[resolved]

        if i + 50 < len(titles):
            time.sleep(0.3)

    return result


def phase_enrich(entries: list[dict]) -> list[dict]:
    """Fetch Wikipedia extracts for saints without hagiography_url."""
    all_names: list[str] = []
    for entry in entries:
        for saint in entry["saints"]:
            if not saint.get("hagiography_url"):
                all_names.extend(_candidate_titles(saint["name"]))
    all_names = list(dict.fromkeys(all_names))  # dedup

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

    return entries
```

- [ ] **Step 2: Wire enrichment into main()**

In `main()`, add after the MOSC web block, before the final print:

```python
    if not args.no_enrich:
        entries = phase_enrich(entries)
```

- [ ] **Step 3: Dry-run with enrichment**

```bash
python3 scripts/import_malankara.py --dry-run
```

Expected: all 6 phases run, Wikipedia enrichment fetches and prints count of descriptions retrieved. Full run should take 30–90 seconds due to Wikipedia rate limiting.

- [ ] **Step 4: Commit**

```bash
git add scripts/import_malankara.py
git commit -m "feat: Wikipedia enrichment phase"
```

---

## Task 10: Generate dataset, verify, and commit

**Files:**
- Generate: `backend/app/data/traditions/malankara_saints.json`

- [ ] **Step 1: Run full import**

```bash
python3 scripts/import_malankara.py \
    --out backend/app/data/traditions/malankara_saints.json
```

Expected output (approximately):
```
Phase 1: Malankara ICS...
  N raw events
  M substantive entries
Phase 2: Syriac Patriarchate ICS...
  ...
Phase 3: Panjangom PDF...
  ...
Phase 4: syriacorthodoxresources.org...
  ...
Phase 5: mosc-temp.com...
  ...
Phase 6: Wikipedia enrichment (N candidates)...
  Got M descriptions
Wrote X entries (Y saints, Z enriched) → backend/app/data/traditions/malankara_saints.json
```

- [ ] **Step 2: Spot-check the output**

```bash
python3 -c "
import json
with open('backend/app/data/traditions/malankara_saints.json') as f:
    d = json.load(f)
print(f'Total entries: {len(d)}')
print(f'Total saints: {sum(len(e[\"saints\"]) for e in d)}')

# Verify Christmas is Dec 25, not Jan 7
dec25 = [e for e in d if e['month_day'] == '12-25']
jan07 = [e for e in d if e['month_day'] == '01-07']
print(f'Dec 25 entries: {len(dec25)}')
print(f'Jan 07 entries: {len(jan07)}')  # should be 0 or minimal

# Show St Thomas feast (July 3 Gregorian)
jul03 = [e for e in d if e['month_day'] == '07-03']
if jul03:
    print('July 3:', [s['name'] for s in jul03[0]['saints']])
"
```

Expected: `Dec 25 entries` ≥ 1 (Nativity), `Jan 07 entries` = 0 (Christmas should NOT appear in January — that's the Julian date).

- [ ] **Step 3: Run backend smoke test**

```bash
cd backend
python -m pytest tests/test_api_smoke.py -v
```

Expected: all pass.

- [ ] **Step 4: Manual API verification**

Start the backend:
```bash
cd backend
uvicorn app.main:app --reload
```

In another terminal:
```bash
curl -s "http://localhost:8000/api/saints?date=2026-12-25&tradition=malankara" | python3 -m json.tool | head -30
```

Expected: returns saints for December 25 (Nativity of Our Lord), `calendar_system: "gregorian"`.

```bash
curl -s "http://localhost:8000/api/saints?date=2026-07-03&tradition=malankara" | python3 -m json.tool | head -20
```

Expected: returns Saint Thomas the Apostle feast (July 3 is the Gregorian feast day for MOSC).

- [ ] **Step 5: Commit dataset and final script**

```bash
git add backend/app/data/traditions/malankara_saints.json scripts/import_malankara.py
git commit -m "feat: add malankara_saints.json dataset from multi-source import"
```

---

## Self-Review: Spec Coverage Check

| Spec requirement | Covered by |
|---|---|
| `config.py` JULIAN→GREGORIAN, remove `data_key` | Task 1 |
| Google Calendar ICS (primary source) | Task 5 |
| Syriac ICS + Julian→Gregorian conversion | Task 6 |
| Panjangom PDF (pdfplumber) | Task 7 |
| syriacorthodoxresources.org (−13 days) | Task 8 |
| mosc-temp.com (Gregorian) | Task 8 |
| Wikipedia enrichment | Task 9 |
| Per-phase `--no-*` flags | Tasks 5–9 |
| `--dry-run` flag | Task 5 |
| Warn-and-continue on network failure | All phase functions |
| Merge: add new, enrich existing, no overwrite | Task 4 |
| Output: `tradition=malankara, calendar=gregorian` | Task 4 |
| pdfplumber in separate requirements file | Task 1 |
| Backend smoke test passes | Task 1 step 4, Task 10 step 3 |
| Lectionary readings excluded | Not implemented (by design) |
| Farley Lawrence synaxarion | Manual/optional (not in tasks — add manually if coverage is insufficient) |
