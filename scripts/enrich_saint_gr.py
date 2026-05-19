#!/usr/bin/env python3
"""
Merge saint_gr_raw.json into greek_saints.json.

Strategy:
  1. For each saint from saint.gr (Gregorian MM-DD key):
     - Look up existing greek_saints.json entries for that day — skip if already present
     - Try Wikipedia to get English name + hagiography URL
     - Add new saints not already in greek_saints.json
  2. Only add saints with English Wikipedia matches (to avoid pure Greek-language entries
     with no English description). Use --include-gr-only to override.

Calendar note: saint.gr uses Gregorian/Revised Julian dates. greek_saints.json also
uses Gregorian keys (CalendarSystem.REVISED). No date conversion needed.

Usage:
    python3 scripts/enrich_saint_gr.py \\
        --raw scripts/saint_gr_raw.json \\
        --greek backend/app/data/traditions/greek_saints.json \\
        [--dry-run] [--include-gr-only] [--delay 0.5]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _name_utils import normalize  # noqa: E402

WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

# Greek honorifics to strip before Wikipedia search
_GR_HONORIFICS = re.compile(
    r'^(?:Άγιος|Αγία|Άγιοι|Άγιες|Όσιος|Οσία|Όσιοι|Ιερομάρτυρας|Μάρτυρας|'
    r'Νεομάρτυρας|Ιεράρχης|Πατριάρχης|Επίσκοπος|Αρχιεπίσκοπος|Πρεσβύτερος|'
    r'Ιερεύς|Μοναχός|Προφήτης|Απόστολος|Ισαπόστολος|Θεοτόκος|Παναγία|'
    r'Οσιομάρτυρας|Αθλοφόρος|Ομολογητής|Ανακομιδή|Σύναξη|Εύρεση)\s+',
    re.IGNORECASE,
)
_PURE_EVENT_GR = re.compile(
    r'^(?:Ανακομιδή|Σύναξη|Εύρεση|Κατάθεση|Μεταφορά|Εγκαίνια|Πανήγυρις|'
    r'Μνήμη|Εορτή|Αποκεφαλισμός|Σύλληψη|Γέννηση|Κοίμηση|Μεταμόρφωση|'
    r'Θεοφάνεια|Υπαπαντή|Εισόδια|Ευαγγελισμός|Υψωσις|Σταύρωση)\b',
    re.IGNORECASE,
)


def _gr_to_search_term(name_gr: str) -> str:
    """Extract a usable search term from a Greek saint name."""
    term = _GR_HONORIFICS.sub("", name_gr).strip()
    # Remove parenthetical years
    term = re.sub(r'\s*\(\d{3,4}.*?\)', '', term).strip()
    # Remove trailing qualifiers like "ο Αγιορείτης" → keep main name
    term = re.sub(r'\s+(?:ο|η|της|του)\s+\w+$', '', term).strip()
    return term


def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _extract_text(page: dict) -> str | None:
    if page.get("missing") is not None:
        return None
    raw = (page.get("extract") or "").strip()
    if len(raw) < 30:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    return " ".join(sentences[:3])[:400].strip()


_SAINT_TERMS = frozenset({
    "saint", "martyr", "hieromartyr", "bishop", "patriarch", "apostle",
    "monk", "nun", "priest", "abbot", "confessor", "deacon", "hermit",
    "venerable", "blessed", "theologian",
})


def _is_religious(text: str) -> bool:
    """Return True only when the extract describes an actual saint or religious figure.

    Requires at least one term from _SAINT_TERMS (saint, martyr, bishop…).
    Broad context words ("orthodox", "christian") are insufficient alone — they
    appear in many non-saint articles (institutions, movements, geography).
    """
    lower = text.lower()
    return any(t in lower for t in _SAINT_TERMS)


def wiki_search(term: str, delay: float) -> dict | None:
    """Search Wikipedia for a saint by name. Returns {name, url, description} or None."""
    if not term or len(term) < 4:
        return None
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
        time.sleep(delay)
        return None

    for hit in hits:
        title = hit["title"]
        if "disambiguation" in title.lower():
            continue
        term_words = [w.lower() for w in re.split(r'\W+', term) if len(w) > 3]
        title_lower = title.lower()
        if not any(w in title_lower for w in term_words):
            continue

        try:
            d2 = _api_get({
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "exintro": "1",
                "exsentences": "3",
                "explaintext": "1",
                "redirects": "1",
            })
            for page in d2.get("query", {}).get("pages", {}).values():
                desc = _extract_text(page)
                if desc and _is_religious(desc):
                    actual_title = page.get("title", title)
                    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
                        actual_title.replace(" ", "_")
                    )
                    time.sleep(delay)
                    return {"name": actual_title, "url": url, "description": desc}
        except Exception:
            pass

        time.sleep(delay * 0.5)

    time.sleep(delay)
    return None


def _build_existing_index(greek_data: list[dict]) -> dict[str, set[int]]:
    """Build {mm_dd: {saint_gr_id, ...}} index from existing greek_saints.json."""
    index: dict[str, set[int]] = {}
    for entry in greek_data:
        mm_dd = entry["month_day"]
        ids = set()
        for s in entry.get("saints", []):
            if s.get("saint_gr_id"):
                ids.add(s["saint_gr_id"])
        index[mm_dd] = ids
    return index


def _build_oca_name_index(oca_path: Path) -> dict[str, set[str]]:
    """Build {mm_dd: {normalized_token, ...}} from OCA Julian data.

    saint.gr uses Gregorian/Revised Julian MM-DD; OCA uses Julian MM-DD.
    For fixed feasts both calendars use the same MM-DD label (Jan 1 = Jan 1),
    so we index OCA names directly by their Julian MM-DD key.
    This lets us detect OCA duplicates without any date conversion.
    """
    if not oca_path.exists():
        return {}
    with oca_path.open(encoding="utf-8") as f:
        oca: list[dict] = json.load(f)
    index: dict[str, set[str]] = {}
    for entry in oca:
        mm_dd = entry["month_day"]
        tokens: set[str] = set()
        for s in entry.get("saints", []):
            for field in (s.get("title", ""), s.get("name", "")):
                for tok in normalize(field).split():
                    if len(tok) >= 4:
                        tokens.add(tok)
        index[mm_dd] = tokens
    return index


def _wiki_name_in_oca(wiki_name: str, oca_tokens: set[str]) -> bool:
    """Return True if the Wikipedia English name overlaps with OCA saints for that day."""
    norm_tokens = [t for t in normalize(wiki_name).split() if len(t) >= 4]
    if not norm_tokens:
        return False
    matches = sum(1 for t in norm_tokens if t in oca_tokens)
    # Match if ≥1 strong token overlaps AND coverage ≥ 30%
    return matches >= 1 and matches / len(norm_tokens) >= 0.3


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge saint.gr data into greek_saints.json")
    parser.add_argument("--raw", default="scripts/saint_gr_raw.json",
                        help="Path to saint_gr_raw.json (default: scripts/saint_gr_raw.json)")
    parser.add_argument("--greek", default="backend/app/data/traditions/greek_saints.json",
                        help="Path to greek_saints.json")
    parser.add_argument("--oca", default="backend/app/data/oca_julian.json",
                        help="Path to oca_julian.json for cross-reference dedup")
    parser.add_argument("--out", default=None,
                        help="Output path (default: overwrite --greek)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be added, write nothing")
    parser.add_argument("--include-gr-only", action="store_true",
                        help="Add saints even without English Wikipedia match (Greek name only)")
    parser.add_argument("--delay", type=float, default=0.4,
                        help="Delay between Wikipedia API calls (default 0.4)")
    args = parser.parse_args()

    raw_path = Path(args.raw)
    greek_path = Path(args.greek)
    out_path = Path(args.out) if args.out else greek_path

    with raw_path.open(encoding="utf-8") as f:
        raw: dict[str, list[dict]] = json.load(f)
    with greek_path.open(encoding="utf-8") as f:
        greek_data: list[dict] = json.load(f)

    oca_index = _build_oca_name_index(Path(args.oca))
    print(f"OCA index: {len(oca_index)} days loaded", file=sys.stderr)

    existing_index = _build_existing_index(greek_data)
    # Name-based dedup from existing greek_saints
    existing_names: set[str] = set()
    for entry in greek_data:
        for s in entry.get("saints", []):
            n = normalize(s.get("title") or s.get("name", ""))
            if n:
                existing_names.add(n)

    added = 0
    skipped_existing = 0
    skipped_no_wiki = 0
    skipped_event = 0

    for mm_dd in sorted(raw.keys()):
        saints_raw = raw[mm_dd]
        existing_ids = existing_index.get(mm_dd, set())

        for sr in saints_raw:
            saint_id = sr["id"]
            name_gr = sr["name_gr"]

            # Skip if already in greek_saints by ID
            if saint_id in existing_ids:
                skipped_existing += 1
                continue

            # Skip pure liturgical events (feast day descriptions, not saints)
            if _PURE_EVENT_GR.match(name_gr):
                skipped_event += 1
                continue

            search_term = _gr_to_search_term(name_gr)
            if not search_term or len(search_term) < 4:
                skipped_event += 1
                continue

            wiki = wiki_search(search_term, args.delay)

            if not wiki:
                if not args.include_gr_only:
                    skipped_no_wiki += 1
                    continue
                # Include with Greek name only
                english_name = search_term
                wiki_url = None
                wiki_desc = None
            else:
                english_name = wiki["name"]
                wiki_url = wiki["url"]
                wiki_desc = wiki["description"]

            # Skip if already in OCA for this day (same fixed feast, different calendar display)
            oca_tokens = oca_index.get(mm_dd, set())
            if oca_tokens and _wiki_name_in_oca(english_name, oca_tokens):
                skipped_existing += 1
                continue

            # Skip if English name already in existing greek_saints
            norm_en = normalize(english_name)
            if norm_en in existing_names:
                skipped_existing += 1
                continue

            new_saint = {
                "name": english_name,
                "title": english_name,
                "feast_type": "Saint",
                "hagiography_url": wiki_url,
                "notes": wiki_desc,
                "canonized_by": "Ecumenical Patriarchate of Constantinople",
                "canonization_scope": "local",
                "year_canonized": None,
                "saint_gr_id": saint_id,
                "saint_gr_url": sr["url"],
                "name_gr": name_gr,
            }

            if args.dry_run:
                print(f"  {mm_dd} [{saint_id}] {name_gr[:40]:40} → {english_name[:50]}")
            else:
                # Find or create entry for this mm_dd
                entry = next((e for e in greek_data if e["month_day"] == mm_dd), None)
                if entry is None:
                    entry = {
                        "month_day": mm_dd,
                        "tradition": "greek",
                        "calendar": "revised",
                        "saints": [],
                    }
                    greek_data.append(entry)
                entry["saints"].append(new_saint)
                existing_ids.add(saint_id)
                existing_names.add(norm_en)

            added += 1

    print(
        f"\nAdded: {added}  Existing: {skipped_existing}  "
        f"No Wiki: {skipped_no_wiki}  Event/skip: {skipped_event}",
        file=sys.stderr,
    )

    if args.dry_run:
        return

    # Sort entries by month_day
    greek_data.sort(key=lambda e: e["month_day"])

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(greek_data, f, ensure_ascii=False, indent=2)
    print(f"Wrote → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
