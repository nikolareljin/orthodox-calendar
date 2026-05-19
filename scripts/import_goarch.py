#!/usr/bin/env python3
"""
Scrape the GOARCH chapel calendar and extract all saints with their contentids.

URL pattern:
    Monthly calendar: https://www.goarch.org/chapel/calendar?month=M&year=YYYY
    Saint page:       https://www.goarch.org/chapel/saints?contentid=NNNNN

Output (goarch_raw.json):
    { "MM-DD": [{"name": "...", "contentid": NNN, "goarch_url": "https://..."}] }

Saints in GOARCH are Revised Julian (New Calendar). Fixed feast dates are the
same as Old Julian MM-DD, so the output keys map directly onto oca_julian.json
without any date conversion.

Usage:
    python3 scripts/import_goarch.py [--year 2024] [--delay 1.5] [--out scripts/goarch_raw.json]
    python3 scripts/import_goarch.py --dry-run
"""

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed. Run: pip install playwright && playwright install chromium",
          file=sys.stderr)
    sys.exit(1)

CHAPEL_BASE = "https://www.goarch.org/chapel"
CALENDAR_URL = CHAPEL_BASE + "/calendar"
SAINT_URL_TEMPLATE = CHAPEL_BASE + "/saints?contentid={contentid}"

# ---------------------------------------------------------------------------
# Julian date handling
# ---------------------------------------------------------------------------
# GOARCH uses the New (Revised Julian) Calendar, whose fixed feast dates share
# the same MM-DD as the Old Julian calendar:
#   New Calendar Christmas  = "12-25" civil Dec 25
#   Old Julian Christmas    = "12-25" civil Jan  7  (13-day offset in 21st c.)
# Both churches say "Christmas is December 25" on their own calendar.
# Because all traditional Orthodox fixed feast dates are identical MM-DD in
# both Old Julian and Revised Julian, GOARCH dates scrape directly as Julian
# storage keys (MM-DD) with NO arithmetic conversion needed.
#
# The only exception: modern saints canonized on a specific Gregorian civil
# date (rare in Eastern churches). Pass --civil-to-julian to apply -13 days
# for those cases, or handle them manually after the initial import.
# ---------------------------------------------------------------------------

import calendar as _cal_module  # noqa: E402  (used for leap-year day count)
from datetime import date as _date, timedelta as _td


def gregorian_to_julian_mm_dd(month: int, day: int, year: int = 2024) -> str:
    """Convert a Gregorian civil date to its Julian calendar MM-DD equivalent.

    For 21st-century dates the Julian calendar is 13 days BEHIND Gregorian,
    so Julian date = Gregorian date − 13 days.  Only needed for saints whose
    feast was assigned to a specific Gregorian civil date; traditional liturgical
    feasts already share the same MM-DD in both calendars.
    """
    greg = _date(year, month, day)
    julian = greg - _td(days=13)
    return f"{julian.month:02d}-{julian.day:02d}"


_CONTENTID_RE = re.compile(r"contentid=(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"contentdate=(\d+)[%/](\d+)[%/](\d+)", re.IGNORECASE)
# URL-decoded slash is %2F
_DATE_DECODED_RE = re.compile(r"contentdate=(\d+)/(\d+)/(\d+)")


def _parse_contentid(href: str) -> int | None:
    m = _CONTENTID_RE.search(href)
    return int(m.group(1)) if m else None


def _parse_month_day(href: str, month: int) -> str | None:
    """Extract MM-DD from contentdate param or fall back to provided month."""
    # Try URL-decoded first
    href_decoded = href.replace("%2F", "/")
    m = _DATE_DECODED_RE.search(href_decoded)
    if m:
        mo, day = int(m.group(1)), int(m.group(2))
        return f"{mo:02d}-{day:02d}"
    m2 = _DATE_RE.search(href)
    if m2:
        mo, day = int(m2.group(1)), int(m2.group(2))
        return f"{mo:02d}-{day:02d}"
    return None


def scrape_month(page, month: int, year: int, delay: float) -> dict[str, list[dict]]:
    """Return {MM-DD: [{name, contentid, goarch_url}]} for one calendar month."""
    url = f"{CALENDAR_URL}?month={month}&year={year}"
    page.goto(url, wait_until="networkidle", timeout=30000)

    # Extract all saint links from the calendar
    # GOARCH chapel calendar links look like:
    #   <a href="/chapel/saints?contentid=102&contentdate=1%2F7%2F2024">Saint John...</a>
    raw = page.evaluate(r"""
    () => {
        const results = [];
        // Try multiple selectors as GOARCH may restructure layout
        const selectors = [
            'a[href*="contentid"]',
            '.chapel-calendar a',
            '.kal-event a',
            'td a[href*="/chapel/saints"]',
        ];
        const seen = new Set();
        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href.includes('contentid')) return;
                if (seen.has(href)) return;
                seen.add(href);

                // Try to find the day from parent cell
                let day = null;
                let el = a;
                for (let i = 0; i < 6; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    // data-day attribute or td with day number div
                    if (el.dataset && el.dataset.day) { day = parseInt(el.dataset.day); break; }
                    const dayEl = el.querySelector('.day-number, .portlet-column-count, span.day');
                    if (dayEl) {
                        const n = parseInt(dayEl.textContent.trim());
                        if (!isNaN(n) && n >= 1 && n <= 31) { day = n; break; }
                    }
                    // td with first text node being a number
                    if (el.tagName === 'TD') {
                        const txt = el.textContent.trim().split('\n')[0].trim();
                        const n = parseInt(txt);
                        if (!isNaN(n) && n >= 1 && n <= 31) { day = n; break; }
                    }
                }

                results.push({
                    href: href,
                    name: a.textContent.trim().replace(/\s+/g, ' '),
                    day: day,
                });
            });
            if (results.length > 0) break;
        }
        return results;
    }
    """)

    by_day: dict[str, list[dict]] = defaultdict(list)
    seen_ids: set[int] = set()

    for item in raw:
        href = item.get("href", "")
        name = item.get("name", "").strip()
        day_num = item.get("day")
        if not name or not href:
            continue

        contentid = _parse_contentid(href)
        if contentid is None:
            continue
        if contentid in seen_ids:
            continue
        seen_ids.add(contentid)

        # Determine MM-DD from href or from day_num
        month_day = _parse_month_day(href, month)
        if not month_day and day_num:
            month_day = f"{month:02d}-{day_num:02d}"
        if not month_day:
            print(f"  WARN: could not determine date for {name!r} (contentid={contentid})",
                  file=sys.stderr)
            continue

        entry = {
            "name": name,
            "contentid": contentid,
            "goarch_url": SAINT_URL_TEMPLATE.format(contentid=contentid),
        }
        by_day[month_day].append(entry)

    return dict(by_day)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape GOARCH chapel calendar via Playwright")
    parser.add_argument("--year", type=int, default=2024,
                        help="Calendar year to scrape (use a leap year for 366 days; default 2024)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between month-page requests (default 1.5)")
    parser.add_argument("--out", default="scripts/goarch_raw.json",
                        help="Output JSON path (default: scripts/goarch_raw.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape January only, print summary, do not write output")
    parser.add_argument("--civil-to-julian", action="store_true",
                        help="Convert GOARCH civil-Gregorian dates to Julian MM-DD (−13 days). "
                             "Not needed for traditional liturgical feasts (same MM-DD in both "
                             "calendars) but useful for recently canonized saints on civil dates.")
    args = parser.parse_args()

    months = range(1, 2) if args.dry_run else range(1, 13)
    out_path = Path(args.out)
    all_saints: dict[str, list[dict]] = {}

    print(f"Scraping GOARCH chapel calendar year={args.year}...", file=sys.stderr)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        for month in months:
            print(f"  Month {month:02d}/{args.year}...", file=sys.stderr, end=" ")
            try:
                result = scrape_month(page, month, args.year, args.delay)
                # Optionally shift dates from civil-Gregorian to Julian (−13 days)
                if args.civil_to_julian:
                    shifted: dict[str, list[dict]] = {}
                    for mm_dd, entries in result.items():
                        mo, dd = int(mm_dd[:2]), int(mm_dd[3:])
                        julian_key = gregorian_to_julian_mm_dd(mo, dd, args.year)
                        shifted.setdefault(julian_key, []).extend(entries)
                    result = shifted
                count = sum(len(v) for v in result.values())
                print(f"{count} saints across {len(result)} days", file=sys.stderr)
                for mm_dd, entries in result.items():
                    all_saints.setdefault(mm_dd, [])
                    seen_ids = {e["contentid"] for e in all_saints[mm_dd]}
                    for e in entries:
                        if e["contentid"] not in seen_ids:
                            all_saints[mm_dd].append(e)
                            seen_ids.add(e["contentid"])
            except Exception as exc:
                print(f"WARN: month {month} failed: {exc}", file=sys.stderr)

            if month < 12 and not args.dry_run:
                time.sleep(args.delay)

        browser.close()

    total = sum(len(v) for v in all_saints.values())
    print(f"\nTotal: {total} saints across {len(all_saints)} days", file=sys.stderr)

    if args.dry_run:
        for mm_dd, entries in sorted(all_saints.items()):
            for e in entries:
                print(f"  {mm_dd}  {e['name']!r}  contentid={e['contentid']}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(dict(sorted(all_saints.items())), f, ensure_ascii=False, indent=2)
    print(f"Wrote → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
