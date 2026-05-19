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
# Stealth: hide Playwright/automation signals from Cloudflare bot detection
# ---------------------------------------------------------------------------

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-component-update",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--start-maximized",
]

# Injected before every page script — patches all CF-visible automation signals.
_STEALTH_JS = """
// 1. Hide webdriver flag (primary CF signal)
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
try { delete navigator.__proto__.webdriver; } catch(_) {}

// 2. Realistic plugin list (headless Chromium has none)
const _pluginData = [
    {name:'Chrome PDF Plugin',   filename:'internal-pdf-viewer',
     description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',   filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',
     description:''},
    {name:'Native Client',       filename:'internal-nacl-plugin',
     description:''},
];
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = _pluginData.map(p => Object.assign(Object.create(Plugin.prototype), p));
        Object.setPrototypeOf(arr, PluginArray.prototype);
        return arr;
    }
});

// 3. Languages
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

// 4. window.chrome runtime (absent in automated Chromium)
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) window.chrome.runtime = {};
if (!window.chrome.loadTimes) window.chrome.loadTimes = function(){};
if (!window.chrome.csi) window.chrome.csi = function(){};

// 5. Permissions API — CF checks this for automation
const _origPermQuery = window.navigator.permissions?.query?.bind(navigator.permissions);
if (_origPermQuery) {
    window.navigator.permissions.__proto__.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({state: Notification.permission, onchange: null})
            : _origPermQuery(params);
}

// 6. Hide Playwright-specific globals
delete window.__playwright;
delete window.__pw_manual;
"""

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

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

from datetime import date as _date, timedelta as _td


def gregorian_to_julian_mm_dd(month: int, day: int, year: int = 2024) -> str:
    """Convert a Gregorian civil date to its Julian calendar MM-DD equivalent via JDN.

    The Gregorian↔Julian offset grows over time (13 days in 1900–2099, 14 from 2100,
    etc.), so the offset is computed from the year via Julian Day Number arithmetic
    rather than being hardcoded.
    """
    greg = _date(year, month, day)
    # Gregorian JDN
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    # JDN → Julian calendar
    c = jdn + 32082
    d4 = (4 * c + 3) // 1461
    e4 = c - (1461 * d4) // 4
    m4 = (5 * e4 + 2) // 153
    jday = e4 - (153 * m4 + 2) // 5 + 1
    jmonth = m4 + 3 - 12 * (m4 // 10)
    return f"{jmonth:02d}-{jday:02d}"


_CONTENTID_RE = re.compile(r"contentid=(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"contentdate=(\d+)[%/](\d+)[%/](\d+)", re.IGNORECASE)
# URL-decoded slash is %2F
_DATE_DECODED_RE = re.compile(r"contentdate=(\d+)/(\d+)/(\d+)")


def _parse_contentid(href: str) -> int | None:
    m = _CONTENTID_RE.search(href)
    return int(m.group(1)) if m else None


def _parse_month_day(href: str) -> str | None:
    """Extract MM-DD from contentdate param in a GOARCH chapel saint href."""
    # Decode percent-encoding case-insensitively (%2F and %2f both → /)
    import urllib.parse as _up
    href_decoded = _up.unquote(href)
    m = _DATE_DECODED_RE.search(href_decoded)
    if m:
        mo, day = int(m.group(1)), int(m.group(2))
        return f"{mo:02d}-{day:02d}"
    m2 = _DATE_RE.search(href)
    if m2:
        mo, day = int(m2.group(1)), int(m2.group(2))
        return f"{mo:02d}-{day:02d}"
    return None


def _navigate(page, url: str) -> None:
    """Navigate to url and wait for network to settle.

    If CF challenge appears, polls every 2 s until the title is no longer
    "Just a moment..." — no hard timeout; prints a reminder every 30 s so the
    user knows to click/solve in the browser window.
    """
    import time as _time
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    warned_at = _time.time()
    while True:
        title = page.title()
        if "just a moment" not in title.lower():
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return
        now = _time.time()
        if now - warned_at >= 30:
            print(
                "\n  [CF] Still on challenge page — solve it in the browser window...",
                file=sys.stderr,
            )
            warned_at = now
        _time.sleep(2)


def scrape_month(page, month: int, year: int) -> dict[str, list[dict]]:
    """Return {MM-DD: [{name, contentid, goarch_url}]} for one calendar month."""
    url = f"{CALENDAR_URL}?month={month}&year={year}"
    _navigate(page, url)

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
        month_day = _parse_month_day(href)
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
    parser.add_argument("--no-headless", action="store_true",
                        help="Run browser with visible window (required to pass Cloudflare on local machine)")
    parser.add_argument("--profile-dir", default=None,
                        help="Persistent Chrome profile directory path (default: scripts/.goarch-profile). "
                             "Reusing a profile that already has cf_clearance skips the CF challenge.")
    args = parser.parse_args()

    months = range(1, 2) if args.dry_run else range(1, 13)
    out_path = Path(args.out)
    all_saints: dict[str, list[dict]] = {}
    headless = not args.no_headless

    profile_dir = Path(args.profile_dir) if args.profile_dir else Path(__file__).parent / ".goarch-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scraping GOARCH chapel calendar year={args.year} headless={headless}...", file=sys.stderr)
    print(f"Browser profile: {profile_dir}", file=sys.stderr)

    # Prefer system Chromium (real binary = more realistic fingerprint than
    # Playwright's bundled Chromium).  Fall back to Playwright's own build.
    _SYSTEM_CHROME_CANDIDATES = [
        "/snap/bin/chromium",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    executable_path = next(
        (p for p in _SYSTEM_CHROME_CANDIDATES if Path(p).exists()), None
    )
    if executable_path:
        print(f"Using system browser: {executable_path}", file=sys.stderr)
    else:
        print("Using Playwright bundled Chromium", file=sys.stderr)

    with sync_playwright() as pw:
        # Persistent context keeps cf_clearance cookie across navigations and reruns.
        context = pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            executable_path=executable_path,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            args=_STEALTH_ARGS,
        )
        page = context.new_page()
        page.add_init_script(_STEALTH_JS)

        # Pre-flight: navigate to goarch.org root once to acquire cf_clearance.
        # After solving the challenge here, subsequent month-page navigations
        # will reuse the cookie and should not be challenged again.
        print("  Pre-flight: opening goarch.org to acquire CF clearance cookie...", file=sys.stderr)
        _navigate(page, "https://www.goarch.org/")
        print("  goarch.org loaded. Proceeding to calendar pages...", file=sys.stderr)

        for month in months:
            print(f"  Month {month:02d}/{args.year}...", file=sys.stderr, end=" ")
            try:
                result = scrape_month(page, month, args.year)
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

        context.close()

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
