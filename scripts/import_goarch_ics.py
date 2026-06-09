#!/usr/bin/env python3
"""
Import GOARCH (Greek Orthodox Archdiocese of America) saints from the annual
planner ICS file.

Source: GOARCH annual planner ICS
  https://www.goarch.org/documents/32058/15097777/planner2025-en.ics/...
  (Download from the Wayback Machine or directly from a browser session;
   the site requires Cloudflare challenge resolution.)

ICS format:
  - CALSCALE:GREGORIAN (Gregorian dates used as keys)
  - One VEVENT per day (365 events per year)
  - DTSTART;VALUE=DATE:YYYYMMDD
  - SUMMARY: primary feast/saint name
  - DESCRIPTION: "Saints, Feasts, and Readings for MM/DD/YYYY\n\n
                  Saints and Feasts: name1; name2; ...\n\n
                  Epistle Reading: ...\n\nGospel Reading: ..."

Calendar notes:
  GOARCH uses the New Calendar (Revised Julian). For fixed feasts, the
  Gregorian civil date equals the Revised Julian MM-DD key, so no arithmetic
  conversion is needed. We store dates as "MM-DD" from the DTSTART field.

Usage:
    python3 scripts/import_goarch_ics.py \\
        --ics /tmp/goarch2025.ics \\
        --out backend/app/data/traditions/greek_saints.json

    python3 scripts/import_goarch_ics.py \\
        --ics /tmp/goarch2025.ics \\
        --merge \\
        --out backend/app/data/traditions/greek_saints.json

    python3 scripts/import_goarch_ics.py \\
        --ics /tmp/goarch2025.ics \\
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ICS parsing
# ---------------------------------------------------------------------------

_VEVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
_DTSTART_RE = re.compile(r"DTSTART[^:]*:(\d{4})(\d{2})(\d{2})")
_SUMMARY_RE = re.compile(r"^SUMMARY:(.+)$", re.MULTILINE)
_DESC_RE = re.compile(r"^DESCRIPTION:(.+)$", re.MULTILINE | re.DOTALL)
# Match the saints section after unescaping (actual \n\n newlines, not ICS-escaped \n\n)
_SAINTS_SECTION_RE = re.compile(r"Saints and Feasts:(.*?)(?:\n\n|$)", re.DOTALL)

# Movable-feast day descriptors — these are year-specific Paschaltide/Pentecostarion
# entries that appear in the ICS for a particular civil date but are not fixed feasts.
# Storing them as static "MM-DD" saints would break year-boundary queries.
#
# Note: "Apodosis of [fixed feast]" (Transfiguration, Dormition, Nativity of Theotokos,
# Elevation of Cross, Presentation, Nativity of Christ) are fixed dates and are kept.
# "Apodosis of Pascha" and "Apodosis of … Holy Ascension/Pentecost" are movable.
_MOVABLE_FEAST_RE = re.compile(
    # Weekday-of-Paschaltide markers ("4th Tuesday after Pascha")
    r"^\d+(?:st|nd|rd|th)?\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|after (?:pascha|pentecost)"
    # Named Bright/Cheesefare/Meatfare days
    r"|bright (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)"
    r"|cheesefare|meatfare"
    # Pascha itself and Thomas Sunday
    r"|(?:great\s+and\s+)?holy\s+pascha|thomas\s+sunday"
    # Movable Apodosis/leave-taking of Pascha-cycle feasts
    r"|apodosis\s+of\s+(?:pascha|the\s+feast\s+of\s+the\s+holy|holy\s+(?:ascension|pentecost))"
    # Holy Ascension and Holy Pentecost as standalone feast titles
    r"|^holy\s+(?:ascension|pentecost)$"
    # Saturday of the Departed / Soul Saturdays
    r"|saturday of the departed|soul saturday"
    # Lent-period Sunday titles
    r"|holy and great|sunday of (?:orthodoxy|the prodigal|meatfare|cheesefare|the publican)",
    re.IGNORECASE,
)


def _unfold(text: str) -> str:
    """Remove ICS line-folding (CRLF/LF + whitespace continuation)."""
    return re.sub(r"\r?\n[ \t]", "", text)


def _unescape(text: str) -> str:
    """Unescape ICS text property values."""
    return text.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_events(ics_text: str) -> list[dict]:
    """Parse VEVENT blocks from ICS text into structured dicts."""
    unfolded = _unfold(ics_text)
    events = []
    for block in _VEVENT_RE.finditer(unfolded):
        ev = block.group(1)

        m_dt = _DTSTART_RE.search(ev)
        if not m_dt:
            continue
        month_day = f"{m_dt.group(2)}-{m_dt.group(3)}"

        m_sum = _SUMMARY_RE.search(ev)
        summary = _unescape(m_sum.group(1).strip()) if m_sum else ""

        saints: list[str] = []
        m_desc = _DESC_RE.search(ev)
        if m_desc:
            desc = _unescape(m_desc.group(1))
            m_sf = _SAINTS_SECTION_RE.search(desc)
            if m_sf:
                raw = m_sf.group(1).strip()
                saints = [s.strip() for s in raw.split(";") if s.strip()]

        # Ensure the summary is in the saints list (it may be absent or abbreviated)
        if summary and summary not in saints:
            saints.insert(0, summary)

        events.append({"month_day": month_day, "summary": summary, "saints": saints})

    return events


# ---------------------------------------------------------------------------
# Feast-type detection
# ---------------------------------------------------------------------------

_FEAST_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhieromartyr\b", re.I), "Hieromartyr"),
    (re.compile(r"\bnew martyr\b|\bnew-martyr\b", re.I), "New Martyr"),
    (re.compile(r"\bneomartyr\b", re.I), "New Martyr"),
    (re.compile(r"\bmartyr\b", re.I), "Martyr"),
    (re.compile(r"\bvenerable\b|\bmonk-martyr\b", re.I), "Venerable"),
    (re.compile(r"\bconfessor\b|\bhieroconfessor\b", re.I), "Confessor"),
    (re.compile(r"\brighteous\b", re.I), "Righteous"),
    (re.compile(r"\bequal.to.apostles?\b", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle\b", re.I), "Apostle"),
    (re.compile(r"\bprophet\b|\bprophetess\b", re.I), "Prophet"),
    (re.compile(r"\barchbishop\b|\bpatriar\b|\bmetropolitan\b|\bbishop\b", re.I), "Hierarch"),
    (re.compile(r"\bpriest\b|\bdeacon\b|\bhierodea\b", re.I), "Priest"),
    (re.compile(r"\bsaint\b|\bst\.\b|\bholy\b", re.I), "Saint"),
    (re.compile(
        r"\btransfiguration\b|\bassumption\b|\bnativity\b|\bpresentation\b"
        r"|\bannunciation\b|\bdormition\b|\btheophany\b|\bpentecost\b"
        r"|\beaster\b|\bpassion\b|\bpalm sunday\b|\bexaltation\b|\bcircumcision\b",
        re.I,
    ), "Great Feast"),
]

_TITLE_PREFIXES_TO_STRIP = re.compile(
    r"^(?:Saint|St\.|Holy|Blessed|Venerable|Righteous|Martyrs?|Holy Martyrs?|"
    r"Hieromartyrs?|Apostle|Prophet|Archbishop|Patriarch|Bishop|Metropolitan|"
    r"Equal[- ]to[- ]Apostles?|New Martyr|Neomartyr|Hierarch|Confessor|"
    r"Monk[- ]Martyr|Hermit|Abbess|Abbot|Presbyter|Deacon|Hieroconfessor)\s+",
    re.I,
)


def _feast_type(name: str) -> str:
    for pattern, ft in _FEAST_TYPE_RULES:
        if pattern.search(name):
            return ft
    return "Saint"


def _clean_name(name: str) -> str:
    """Strip leading title prefixes (kept in the title field) to get a clean name."""
    # Remove parenthetical alternates "(also known as X)"
    name = re.sub(r"\s*\(.*?\)", "", name)
    # Normalize whitespace
    return re.sub(r"\s+", " ", name).strip()


# ---------------------------------------------------------------------------
# Convert events → greek_saints.json entries
# ---------------------------------------------------------------------------

def events_to_entries(events: list[dict]) -> list[dict]:
    """Convert parsed ICS events to the greek_saints.json entry format."""
    by_md: dict[str, list[dict]] = {}

    for ev in events:
        md = ev["month_day"]
        seen_names: set[str] = set()

        for saint_name in ev["saints"]:
            # Skip movable-feast day markers — these are year-specific
            if _MOVABLE_FEAST_RE.search(saint_name):
                continue
            name = _clean_name(saint_name)
            if not name or len(name) < 3:
                continue
            norm = name.lower()
            if norm in seen_names:
                continue
            seen_names.add(norm)

            ft = _feast_type(saint_name)
            entry: dict = {
                "name": name,
                "title": name,
                "feast_type": ft,
                "canonized_by": "Ecumenical Patriarchate of Constantinople",
                "canonization_scope": "universal",
            }
            by_md.setdefault(md, []).append(entry)

    return [
        {
            "month_day": md,
            "tradition": "greek",
            "calendar": "revised",
            "saints": saints_list,
        }
        for md, saints_list in sorted(by_md.items())
    ]


# ---------------------------------------------------------------------------
# Merge with existing greek_saints.json
# ---------------------------------------------------------------------------

def _saint_key(s: dict) -> str:
    name = (s.get("name") or s.get("title") or "").lower()
    return re.sub(r"[^a-z]", "", name)


def merge_entries(existing: list[dict], new: list[dict]) -> list[dict]:
    """
    Merge new ICS entries into existing data.

    Per-date: existing saints are preserved. New saints that don't match
    (by normalized name key) are appended.
    """
    existing_by_md: dict[str, dict] = {e["month_day"]: e for e in existing}

    for new_entry in new:
        md = new_entry["month_day"]
        if md not in existing_by_md:
            existing_by_md[md] = new_entry
            continue

        ex_entry = existing_by_md[md]
        ex_keys = {_saint_key(s) for s in ex_entry["saints"]}

        for saint in new_entry["saints"]:
            k = _saint_key(saint)
            if k not in ex_keys:
                ex_entry["saints"].append(saint)
                ex_keys.add(k)

    return [existing_by_md[md] for md in sorted(existing_by_md)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Import GOARCH ICS saints into greek_saints.json")
    parser.add_argument("--ics", required=True, help="Path to GOARCH planner ICS file")
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/greek_saints.json",
        help="Output JSON file (default: backend/app/data/traditions/greek_saints.json)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge new saints into existing file rather than replacing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only, do not write")
    args = parser.parse_args()

    ics_path = Path(args.ics)
    out_path = Path(args.out)

    if not ics_path.exists():
        print(f"ERROR: ICS file not found: {ics_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {ics_path} ...", file=sys.stderr)
    ics_text = ics_path.read_text(encoding="utf-8", errors="replace")
    events = _parse_events(ics_text)
    print(f"  Parsed {len(events)} events", file=sys.stderr)

    new_entries = events_to_entries(events)
    total_new = sum(len(e["saints"]) for e in new_entries)
    print(f"  Generated {len(new_entries)} date entries, {total_new} saints", file=sys.stderr)

    if args.merge and out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"  Merging with {len(existing)} existing entries ...", file=sys.stderr)
        output = merge_entries(existing, new_entries)
    else:
        output = new_entries

    total_out = sum(len(e["saints"]) for e in output)
    print(f"  Output: {len(output)} date entries, {total_out} saints", file=sys.stderr)

    if args.dry_run:
        print("\nDry run — nothing written.", file=sys.stderr)
        # Show sample
        for entry in output[:3]:
            print(f"  {entry['month_day']}: {[s['name'][:40] for s in entry['saints'][:3]]}", file=sys.stderr)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
