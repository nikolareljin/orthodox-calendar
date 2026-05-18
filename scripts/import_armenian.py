#!/usr/bin/env python3
"""
Import Armenian Apostolic Church feast days from armenianchurch.org.

Scrapes the 27 feast pages listed at:
  https://www.armenianchurch.org/en/Liturgical-Calendar/

Each feast page has a date in the <h1> title as "FeastName DD.MM.YYYY".
Fixed feasts are stored as MM-DD keys; moveable feasts (Easter-cycle)
are kept with a moveable flag in the notes field.

Usage:
    python3 scripts/import_armenian.py --out backend/app/data/traditions/armenian_saints.json
    python3 scripts/import_armenian.py --delay 1.0 --out /path/to/output.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.armenianchurch.org"
CALENDAR_URL = f"{BASE_URL}/en/Liturgical-Calendar/"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Feasts that are Easter-cycle moveable (different MM-DD each year)
_MOVEABLE_KEYWORDS = frozenset({
    "lent", "easter", "palm", "passion", "resurrection", "ascension",
    "pentecost", "fast of catechumens", "fast of zacchaeus",
    "paregentan", "holy week", "good friday", "great lent",
})

_FEAST_TYPE_HINTS = {
    "martyrs": "Martyr",
    "martyr": "Martyr",
    "apostle": "Apostle",
    "apostles": "Apostle",
    "fast": "Fast",
    "fasting": "Fast",
    "nativity": "Great Feast",
    "epiphany": "Great Feast",
    "theophany": "Great Feast",
    "ascension": "Great Feast",
    "pentecost": "Great Feast",
    "transfiguration": "Great Feast",
    "assumption": "Great Feast",
    "resurrection": "Great Feast",
    "easter": "Great Feast",
    "virgin": "Saint",
    "saint": "Saint",
    "st.": "Saint",
    "blessed": "Saint",
    "patriarch": "Hierarch",
    "catholicos": "Hierarch",
}

_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_DATE_RANGE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\s*[-–]\s*\d{2}\.\d{2}\.\d{4}\b")


class _LinkExtractor(HTMLParser):
    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href.startswith(self.prefix) and href != self.prefix:
                full = BASE_URL + href if href.startswith("/") else href
                if full not in self.links:
                    self.links.append(full)


class _FeastHeaderExtractor(HTMLParser):
    """Extract feast name + date from armenianchurch.org feast pages.

    Structure:
      <h2 class="news-inner__block-title ...">Feast Name<br>DD.MM.YYYY</h2>
    The name and date are both inside the h2, separated by a <br>.
    """

    def __init__(self):
        super().__init__()
        self._in_feast_h2 = False
        self._in_title_tag = False
        self.header_text = ""
        self.title_text = ""
        self.description = ""
        self._in_p = False
        self._para_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            attrs_dict = dict(attrs)
            cls = attrs_dict.get("class", "")
            if "news-inner__block-title" in cls:
                self._in_feast_h2 = True
        elif tag == "title":
            self._in_title_tag = True
        elif tag == "p" and self._para_count < 2:
            self._in_p = True
        elif tag == "br" and self._in_feast_h2:
            # <br> separates feast name from date — use newline as separator
            self.header_text += "\n"

    def handle_endtag(self, tag):
        if tag == "h2" and self._in_feast_h2:
            self._in_feast_h2 = False
        elif tag == "title":
            self._in_title_tag = False
        elif tag == "p":
            self._in_p = False
            if self.description:
                self._para_count += 1

    def handle_data(self, data):
        if self._in_feast_h2:
            self.header_text += data
        elif self._in_title_tag:
            self.title_text += data
        elif self._in_p and self._para_count < 1:
            stripped = data.strip()
            if stripped and len(stripped) > 20:
                self.description += stripped + " "


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _feast_type(name: str) -> str:
    lower = name.lower()
    for keyword, ft in _FEAST_TYPE_HINTS.items():
        if keyword in lower:
            return ft
    return "Feast"


def _is_moveable(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in _MOVEABLE_KEYWORDS)


def _short_name(title: str) -> str:
    name = re.sub(
        r"^(?:feast\s+of\s+(?:the\s+)?|fast\s+of\s+(?:the\s+)?|"
        r"commemoration\s+of\s+(?:the\s+)?|birth\s+of\s+(?:the\s+)?)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    return name[:1].upper() + name[1:] if name else title


def get_feast_links() -> list[str]:
    html = _fetch(CALENDAR_URL)
    # Links are absolute: https://www.armenianchurch.org/en/Liturgical-Calendar/NN
    seen: set[str] = set()
    links: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        if re.search(r"/en/Liturgical-Calendar/\d+", href):
            full = href if href.startswith("http") else BASE_URL + href
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links


def parse_feast_page(url: str) -> dict | None:
    html = _fetch(url)
    parser = _FeastHeaderExtractor()
    parser.feed(html)

    h1 = parser.header_text.strip()
    title_tag = parser.title_text.strip()
    description = parser.description.strip()

    # Try to find date in h1 first, then title tag
    for text in (h1, title_tag):
        # Skip date ranges (moveable multi-day periods)
        if _DATE_RANGE_RE.search(text):
            m = _DATE_RANGE_RE.search(text)
            range_str = m.group()
            feast_name = text[:m.start()].strip().rstrip("-–").strip()
            if not feast_name:
                feast_name = text
            return {
                "name": feast_name,
                "moveable": True,
                "date_range": range_str,
                "description": description[:300] if description else None,
            }

        m = _DATE_RE.search(text)
        if m:
            dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
            month_day = f"{mm}-{dd}"
            feast_name = text[:m.start()].strip().rstrip("-–").strip()
            if not feast_name:
                feast_name = text.replace(m.group(), "").strip()
            moveable = _is_moveable(feast_name)
            return {
                "name": feast_name,
                "moveable": moveable,
                "month_day": month_day,
                "gregorian_year": int(yyyy),
                "description": description[:300] if description else None,
            }

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Armenian Apostolic feast days")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument(
        "--out",
        default="backend/app/data/traditions/armenian_saints.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--include-moveable",
        action="store_true",
        help="Include moveable feasts (Easter-cycle) in output",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching Armenian liturgical calendar from armenianchurch.org...", file=sys.stderr)

    links = get_feast_links()
    print(f"  Found {len(links)} feast pages", file=sys.stderr)

    by_month_day: dict[str, list] = {}

    for url in links:
        time.sleep(args.delay)
        try:
            feast = parse_feast_page(url)
            if not feast:
                print(f"  SKIP (no date found): {url}", file=sys.stderr)
                continue

            name = feast["name"]
            moveable = feast.get("moveable", False)

            if moveable:
                print(f"  MOVEABLE: {name} ({feast.get('date_range', '?')})", file=sys.stderr)
                if not args.include_moveable:
                    continue
                month_day = None
            else:
                month_day = feast.get("month_day")
                print(f"  {month_day}: {name}", file=sys.stderr)

            if not month_day:
                continue

            saint = {
                "name": _short_name(name),
                "title": name,
                "feast_type": _feast_type(name),
                "hagiography_url": url,
                "notes": feast.get("description") or None,
                "canonized_by": "Armenian Apostolic Church",
                "canonization_scope": "oriental",
                "year_canonized": None,
            }
            by_month_day.setdefault(month_day, []).append(saint)

        except Exception as exc:
            print(f"  ERROR {url}: {exc}", file=sys.stderr)

    output = []
    for month_day in sorted(by_month_day):
        output.append({
            "month_day": month_day,
            "tradition": "armenian",
            "calendar": "gregorian",
            "saints": by_month_day[month_day],
        })

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    print(f"\nWrote {len(output)} entries ({total} feasts) to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
