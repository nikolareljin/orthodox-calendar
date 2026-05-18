#!/usr/bin/env python3
"""
Import Assyrian Church of the East liturgical calendar from
calendar.assyrianchurch.org using Playwright.

The site pre-loads ~4 years of calendar data in the DOM as a sticky-month
grid. This script:
  1. Loads the page once
  2. Extracts all available months (typically current year + 3 future years)
  3. Intersects events across years on the same MM-DD to isolate fixed feasts
     (moveable feasts like Lent Sundays fall on different MM-DD each year and
     are automatically filtered out by the cross-year intersection)
  4. Writes per-month_day entries with tradition="assyrian", calendar="gregorian"

Usage:
    python3 scripts/import_assyrian.py --out backend/app/data/traditions/assyrian_saints.json
    python3 scripts/import_assyrian.py --min-years 1 --out /path/to/output.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

CALENDAR_URL = "https://calendar.assyrianchurch.org/english-liturgical-calendar/"

_SKIP_TEXTS = frozenset({
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "view as:", "month", "list", "today", "→", "←", "",
})


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _short_name(title: str) -> str:
    name = re.sub(
        r"^(?:commemoration\s+of\s+(?:ss?\.?\s+)?|feast\s+of\s+(?:our\s+lord's?\s+)?)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    return name[:1].upper() + name[1:] if name else title


def _feast_type(title: str) -> str:
    lower = title.lower()
    if "feast" in lower and any(w in lower for w in ["lord", "christ", "ascension",
                                                       "pentecost", "epiphany", "nativity"]):
        return "Great Feast"
    if "sunday" in lower:
        return "Sunday"
    if "fast" in lower:
        return "Fast"
    if any(w in lower for w in ["martyr", "passion", "witness"]):
        return "Martyr"
    if "commemoration" in lower or "st." in lower or "ss." in lower or "mar " in lower:
        return "Saint"
    return "Feast"


def scrape_all(page) -> dict[str, dict[str, list[str]]]:
    """
    Extract all calendar data from the pre-loaded DOM.
    Returns: {monthKey: {MM-DD: [event_title, ...]}}
    where monthKey is "YYYYMM".
    """
    raw = page.evaluate(r"""
    () => {
        const output = {};
        const months = document.querySelectorAll('.ics-calendar-month-wrapper');
        months.forEach(m => {
            const label = m.querySelector('h3.ics-calendar-label, .ics-calendar-label');
            if (!label) return;
            const idMatch = label.id.match(/(\d{6})$/);
            if (!idMatch) return;
            const monthKey = idMatch[1]; // "YYYYMM"
            const year = parseInt(monthKey.slice(0, 4));
            const month = parseInt(monthKey.slice(4, 6));

            const cells = m.querySelectorAll('td.has_events');
            if (!cells.length) return;

            const days = {};
            cells.forEach(cell => {
                const dMatch = cell.className.match(/\bd_(\d+)\b/);
                if (!dMatch) return;
                const day = parseInt(dMatch[1]);
                const mm = String(month).padStart(2, '0');
                const dd = String(day).padStart(2, '0');
                const key = mm + '-' + dd;

                const titles = Array.from(cell.querySelectorAll('li.event span.title'))
                    .map(e => e.innerText.trim())
                    .filter(t => t.length >= 4 && !/[\u0700-\u077F]/.test(t));
                if (titles.length) days[key] = titles;
            });

            if (Object.keys(days).length) output[monthKey] = days;
        });
        return output;
    }
    """)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Assyrian Church calendar via Playwright")
    parser.add_argument(
        "--min-years",
        type=int,
        default=2,
        help="Minimum number of years a feast must appear on the same MM-DD to be kept (default: 2; use 1 to keep all)",
    )
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/assyrian_saints.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading Assyrian liturgical calendar from DOM...", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
        page.goto(CALENDAR_URL, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)

        raw = scrape_all(page)
        browser.close()

    years_available = sorted({mk[:4] for mk in raw})
    print(f"  Found {len(raw)} month blocks across years: {', '.join(years_available)}", file=sys.stderr)

    # Group events by (MM-DD, normalized_title) → set of years seen
    # Also track canonical title and example per (MM-DD, norm_title)
    event_years: dict[tuple, set] = defaultdict(set)
    event_info: dict[tuple, str] = {}

    for month_key, days in raw.items():
        year = month_key[:4]
        for mm_dd, titles in days.items():
            for title in titles:
                norm = _clean(title).lower()
                key = (mm_dd, norm)
                event_years[key].add(year)
                if key not in event_info:
                    event_info[key] = _clean(title)

    # Collect fixed feasts: appear on same MM-DD in >= min_years
    by_month_day: dict[str, list[str]] = defaultdict(list)
    for (mm_dd, norm), years in event_years.items():
        if len(years) >= args.min_years:
            by_month_day[mm_dd].append(event_info[(mm_dd, norm)])

    # Build output
    output = []
    for month_day in sorted(by_month_day):
        titles = by_month_day[month_day]
        saints = []
        seen: set[str] = set()
        for title in titles:
            norm = title.lower().strip()
            if norm in seen or norm in _SKIP_TEXTS:
                continue
            seen.add(norm)
            saints.append({
                "name": _short_name(title),
                "title": title,
                "feast_type": _feast_type(title),
                "hagiography_url": None,
                "notes": None,
                "canonized_by": None,
                "canonization_scope": "church-of-the-east",
                "year_canonized": None,
            })
        if saints:
            output.append({
                "month_day": month_day,
                "tradition": "assyrian",
                "calendar": "gregorian",
                "saints": saints,
            })

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_saints = sum(len(e["saints"]) for e in output)
    print(
        f"\nWrote {len(output)} entries ({total_saints} feasts) to {out_path}",
        file=sys.stderr,
    )
    print(
        f"(Cross-year intersection with min_years={args.min_years} filters moveable feasts)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
