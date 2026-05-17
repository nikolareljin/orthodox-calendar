#!/usr/bin/env python3
"""
Import Armenian Apostolic Church saints from Wikipedia.

Source: https://en.wikipedia.org/wiki/Calendar_of_saints_(Armenian_Apostolic_Church)

Parses the "Days of observance - 2018" calendar (===Month=== / * DD Name format).
Fixed saints' days recur at the same date each year; Easter-cycle entries
(Great Lent days, "Fast Day" stubs, Barekendan, etc.) are skipped unless
--include-moveable is passed.

Enrichment runs in two passes:
  1. Wikilinks embedded in each calendar line → batch-fetch extracts (fast)
  2. Search fallback for entries without wikilinks → Wikipedia search API

Pass --no-enrich to skip all enrichment.

Usage:
    python3 scripts/import_armenian_wiki.py \
        --out backend/app/data/traditions/armenian_saints.json

    python3 scripts/import_armenian_wiki.py --merge \
        --out backend/app/data/traditions/armenian_saints.json

    python3 scripts/import_armenian_wiki.py --no-enrich \
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

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGE = "Calendar of saints (Armenian Apostolic Church)"
WIKI_URL_BASE = "https://en.wikipedia.org/wiki/Calendar_of_saints_(Armenian_Apostolic_Church)"

_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_MOVEABLE_KEYWORDS = frozenset({
    "great lent", "lent", "palm sunday", "holy week", "good friday",
    "easter", "resurrection", "ascension", "pentecost",
    "fast of the catechumens", "fast of zacchaeus",
    "barekendan", "paregentan",
    "first day of", "second day of", "third day of", "fourth day of",
    "fifth day of", "sixth day of", "seventh day of", "eighth day of",
    "ninth day of", "tenth day of", "eleventh day of",
    "fortieth day of", "fiftieth day of",
    "sunday after", "saturday of",
    "day of great lent", "day of the fast", "day of nativity",
})

_BARE_FAST_RE = re.compile(r"^fast\.?\s*(day\.?)?$", re.IGNORECASE)

_FEAST_TYPE_HINTS = [
    (re.compile(r"hieromartyr", re.I), "Hieromartyr"),
    (re.compile(r"\bnew martyr\b", re.I), "New Martyr"),
    (re.compile(r"\bmartyr(s)?\b", re.I), "Martyr"),
    (re.compile(r"\bvirgin\b", re.I), "Virgin"),
    (re.compile(r"\bconfessor\b", re.I), "Confessor"),
    (re.compile(r"equal.to.apostle", re.I), "Equal-to-Apostles"),
    (re.compile(r"\bapostle(s)?\b", re.I), "Apostle"),
    (re.compile(r"catholicos|patriarch|bishop|metropolitan|deacon|priest", re.I), "Hierarch"),
    (re.compile(r"prophet", re.I), "Prophet"),
    (re.compile(r"fast|fasting|lent|barekendan", re.I), "Fast"),
    (re.compile(r"nativity|theophany|transfiguration|ascension|pentecost|presentation|annunciation|assumption", re.I), "Great Feast"),
    (re.compile(r"feast|remembrance|commemoration", re.I), "Feast"),
]

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Targets that are too generic for enrichment (abstract concepts, councils)
_SKIP_TARGETS = frozenset({
    "great lent", "holy week", "first council of constantinople",
    "seventy disciples", "nativity fast",
})

# Search results pointing back to the source calendar are useless
_BAD_SEARCH_TITLES = frozenset({
    "calendar of saints (armenian apostolic church)",
    "armenian apostolic church",
    "armenian calendar",
})

# Prefixes stripped before using the name as a search/direct-fetch term
_NAME_PREFIXES = re.compile(
    r"^(?:the\s+)?(?:holy\s+)?(?:blessed\s+)?(?:saints?\s+|st\.\s+|sts\.\s+)"
    r"|^(?:birth|feast\s+day?|feast|remembrance|commemoration|nativity|"
    r"presentation|annunciation|assumption)\s+of\s+(?:the\s+)?(?:saint\s+|holy\s+)?",
    re.IGNORECASE,
)

# Entry names that are purely liturgical with no specific person to search for
_PURE_LITURGICAL_RE = re.compile(
    r"^(?:eve|day|week|fast|fasting|sunday|monday|tuesday|wednesday|"
    r"thursday|friday|saturday)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _fetch_wikitext() -> str:
    data = _api_get({"action": "parse", "page": WIKI_PAGE, "prop": "wikitext"})
    return data["parse"]["wikitext"]["*"]


def _extract_text(page: dict) -> str | None:
    """Clean and cap the extract from a Wikipedia API page object."""
    if page.get("missing") is not None:
        return None
    raw = (page.get("extract") or "").strip()
    if len(raw) < 30:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    return " ".join(sentences[:3])[:400].strip()


def fetch_extracts(titles: list[str], delay: float = 0.3) -> dict[str, dict]:
    """
    Batch-fetch Wikipedia intro extracts for a list of page titles.
    Returns {title: {description, url}}.
    """
    result: dict[str, dict] = {}

    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
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
            print(f"  WARN batch fetch failed: {exc}", file=sys.stderr)
            continue

        # Build redirect/normalisation map so original titles resolve
        norm: dict[str, str] = {}
        for r in data.get("query", {}).get("redirects", []) + data.get("query", {}).get("normalized", []):
            norm[r["from"]] = r["to"]

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            desc = _extract_text(page)
            if not desc:
                continue
            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            entry = {"description": desc, "url": url}
            result[title] = entry

        for orig in batch:
            resolved = norm.get(orig, orig)
            if resolved in result and orig not in result:
                result[orig] = result[resolved]

        if i + 50 < len(titles):
            time.sleep(delay)

    return result


def _search_term(name: str) -> str:
    """Strip saint/feast prefixes; keep enough words for a specific search."""
    term = _NAME_PREFIXES.sub("", name).strip()
    # Remove leading possessive articles
    term = re.sub(r"^(?:the\s+holy\s+|the\s+blessed\s+|the\s+)", "", term, flags=re.IGNORECASE).strip()
    return term


_RELIGIOUS_TERMS = frozenset({
    "saint", "martyr", "bishop", "patriarch", "apostle", "pope", "priest",
    "monk", "nun", "virgin", "confessor", "deacon", "church", "christian",
    "church", "blessed", "venerable", "holy", "feast", "liturgy", "orthodox",
    "armenian", "byzantine", "coptic", "catholic", "religious", "faith",
    "theologian", "abbot", "abbess", "hermit",
})

# Common words that match too broadly — require them NOT to be the only match
_WEAK_WORDS = frozenset({
    "thomas", "james", "simon", "peter", "mark", "john", "paul", "stephen",
    "michael", "george", "mary", "andrew", "philip", "matthew", "joseph",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "cross", "relic", "holy", "feast", "companions", "martyrs", "saints",
    "great", "church",
})


def _title_relevant(term: str, title: str) -> bool:
    """
    True if a significant (non-weak) word from term appears in title,
    OR if only weak words match but at least two of them do.
    """
    title_lower = title.lower()
    words = [w for w in re.split(r"\W+", term.lower()) if len(w) > 4]
    if not words:
        return False
    strong = [w for w in words if w not in _WEAK_WORDS and w in title_lower]
    weak = [w for w in words if w in _WEAK_WORDS and w in title_lower]
    return bool(strong) or len(weak) >= 2


def _extract_is_religious(text: str) -> bool:
    """Return True if the extract mentions at least one religious term."""
    lower = text.lower()
    return any(term in lower for term in _RELIGIOUS_TERMS)


def search_enrich(names: list[str], delay: float = 0.5) -> dict[str, dict]:
    """
    For each name, search Wikipedia and fetch the top result if it looks valid.
    Applies a relevance guard so unrelated articles are rejected.
    Returns {original_name: {description, url}}.
    """
    result: dict[str, dict] = {}

    for name in names:
        term = _search_term(name)
        if not term or len(term) < 5:
            continue

        try:
            data = _api_get({
                "action": "query",
                "list": "search",
                "srsearch": term,
                "srlimit": "5",
                "srnamespace": "0",
            })
            hits = data.get("query", {}).get("search", [])
        except Exception:
            continue

        matched_title = None
        for hit in hits:
            title = hit["title"]
            if title.lower() in _BAD_SEARCH_TITLES:
                continue
            if "disambiguation" in title.lower():
                continue
            # Reject if no key word from our search term appears in the result title
            if not _title_relevant(term, title):
                continue
            matched_title = title
            break

        if not matched_title:
            continue

        try:
            data2 = _api_get({
                "action": "query",
                "titles": matched_title,
                "prop": "extracts",
                "exintro": "1",
                "exsentences": "3",
                "explaintext": "1",
                "redirects": "1",
            })
            pages = data2.get("query", {}).get("pages", {})
            for page in pages.values():
                desc = _extract_text(page)
                if desc and _extract_is_religious(desc):
                    title = page.get("title", matched_title)
                    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
                    result[name] = {"description": desc, "url": url}
                    break
        except Exception:
            pass

        time.sleep(delay)

    return result


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _feast_type(name: str) -> str:
    for pattern, ft in _FEAST_TYPE_HINTS:
        if pattern.search(name):
            return ft
    return "Saint"


def _is_moveable(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in _MOVEABLE_KEYWORDS)


def _extract_wikilinks(raw: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(raw)]


def _strip_wikilinks(text: str) -> str:
    return re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", text).strip()


def _best_wiki_target(targets: list[str]) -> str | None:
    for t in targets:
        if t.lower() not in _SKIP_TARGETS and not t.startswith("Category:"):
            return t
    return None


def parse_calendar(wikitext: str) -> list[dict]:
    entries: list[dict] = []
    section_re = re.compile(r"===([A-Za-z]+)===")
    bullet_re = re.compile(r"^\*\s+(\d{1,2})\s+(.+)$")

    parts = section_re.split(wikitext)
    for i in range(1, len(parts), 2):
        month_num = _MONTH_MAP.get(parts[i].strip().lower())
        if not month_num:
            continue
        body = parts[i + 1] if i + 1 < len(parts) else ""

        for line in body.splitlines():
            m = bullet_re.match(line.strip())
            if not m:
                continue
            day, raw = int(m.group(1)), m.group(2).strip()
            wiki_targets = _extract_wikilinks(raw)

            name = _strip_wikilinks(raw)
            name = re.sub(r",\s*fast\.?\s*$", "", name, flags=re.IGNORECASE).strip()
            name = re.sub(r"^fast:\s*", "", name, flags=re.IGNORECASE).strip()

            if not name or _BARE_FAST_RE.match(name):
                continue

            entries.append({
                "month_day": f"{month_num:02d}-{day:02d}",
                "name": name,
                "moveable": _is_moveable(name),
                "wiki_targets": wiki_targets,
            })

    return entries


# ---------------------------------------------------------------------------
# Build output
# ---------------------------------------------------------------------------

def build_output(
    entries: list[dict],
    include_moveable: bool,
    enrichment: dict[str, dict],
) -> list[dict]:
    by_md: dict[str, list] = {}

    for e in entries:
        if e["moveable"] and not include_moveable:
            continue

        # Try wikilink target first, then the entry name itself (search fallback key)
        target = _best_wiki_target(e["wiki_targets"])
        enrich = enrichment.get(target) or enrichment.get(e["name"]) or {}

        saint = {
            "name": e["name"],
            "title": e["name"],
            "feast_type": _feast_type(e["name"]),
            "hagiography_url": enrich.get("url") or WIKI_URL_BASE,
            "notes": enrich.get("description") or (
                "Armenian Apostolic Church calendar" + (" (moveable feast)" if e["moveable"] else "")
            ),
            "canonized_by": "Armenian Apostolic Church",
            "canonization_scope": "oriental",
            "year_canonized": None,
        }
        by_md.setdefault(e["month_day"], []).append(saint)

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
    return [by_md[md] for md in sorted(by_md)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Import Armenian Apostolic saints from Wikipedia")
    parser.add_argument("--out", default="backend/app/data/traditions/armenian_saints.json")
    parser.add_argument("--include-moveable", action="store_true")
    parser.add_argument("--merge", action="store_true",
                        help="Merge into existing file instead of replacing")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Skip all Wikipedia enrichment")
    parser.add_argument("--delay", type=float, default=0.3,
                        help="Delay between API batch requests (seconds)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching wikitext from Wikipedia...", file=sys.stderr)
    wikitext = _fetch_wikitext()
    print("  Parsing calendar entries...", file=sys.stderr)

    entries = parse_calendar(wikitext)
    fixed = [e for e in entries if not e["moveable"]]
    moveable = [e for e in entries if e["moveable"]]
    print(f"  Found {len(entries)} entries ({len(fixed)} fixed, {len(moveable)} moveable)", file=sys.stderr)

    enrichment: dict[str, dict] = {}

    if not args.no_enrich:
        active = fixed + (moveable if args.include_moveable else [])

        # Pass 1: wikilink targets
        link_targets: list[str] = []
        seen: set[str] = set()
        for e in active:
            t = _best_wiki_target(e["wiki_targets"])
            if t and t not in seen:
                link_targets.append(t)
                seen.add(t)

        print(f"  Pass 1: fetching {len(link_targets)} wikilink targets...", file=sys.stderr)
        enrichment.update(fetch_extracts(link_targets, delay=args.delay))
        hit1 = sum(1 for t in link_targets if t in enrichment)
        print(f"    Got {hit1}/{len(link_targets)} descriptions", file=sys.stderr)

        # Pass 2: search fallback for entries still not enriched
        unenriched = [
            e for e in active
            if not enrichment.get(_best_wiki_target(e["wiki_targets"]))
            and not _PURE_LITURGICAL_RE.match(e["name"])
        ]
        search_names = [e["name"] for e in unenriched]
        # Deduplicate
        seen2: set[str] = set()
        search_names = [n for n in search_names if not (n in seen2 or seen2.add(n))]  # type: ignore[func-returns-value]

        print(f"  Pass 2: searching for {len(search_names)} unenriched saints...", file=sys.stderr)
        enrichment.update(search_enrich(search_names, delay=args.delay))
        hit2 = sum(1 for n in search_names if n in enrichment)
        print(f"    Got {hit2}/{len(search_names)} additional descriptions", file=sys.stderr)

    output = build_output(entries, args.include_moveable, enrichment)

    if args.merge and out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            existing = json.load(f)
        output = merge_outputs(existing, output)
        print(f"  Merged with {len(existing)} existing entries", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(e["saints"]) for e in output)
    enriched = sum(
        1 for e in output for s in e["saints"]
        if not (s["notes"] or "").startswith("Armenian Apostolic")
    )
    print(f"\nWrote {len(output)} entries ({total} saints, {enriched} enriched) → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
