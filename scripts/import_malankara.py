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
