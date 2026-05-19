#!/usr/bin/env python3
"""
Generic Wikipedia enrichment pass for any tradition JSON.

Reads a saints JSON file, finds entries with missing hagiography_url or notes,
queries Wikipedia for each, and writes the enriched file back.

Reuses the two-pass approach from import_armenian_wiki.py:
  Pass 1: direct Wikipedia fetch for likely specific saint names
  Pass 2: search API for anything that didn't match in pass 1

Usage:
    python3 scripts/enrich_wiki_generic.py \\
        --input backend/app/data/traditions/assyrian_saints.json \\
        [--force-notes]     # overwrite existing notes too
        [--dry-run]         # print what would be enriched, write nothing
        [--delay 0.5]
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

WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {
    "User-Agent": "orthodox-calendar-importer/1.0 (https://github.com/nikolareljin/orthodox-calendar)"
}

# Prefixes to strip before searching
_NAME_PREFIXES = re.compile(
    r"^(?:the\s+)?(?:holy\s+)?(?:blessed\s+)?(?:saints?\s+|st\.\s+|sts\.\s+|ss\.\s+)"
    r"|^(?:birth|feast\s+day?|feast|remembrance|commemoration|nativity|"
    r"presentation|annunciation|assumption|exaltation|dormition)\s+of\s+(?:the\s+)?(?:saint\s+|holy\s+)?",
    re.IGNORECASE,
)
_PURE_LITURGICAL_RE = re.compile(
    r"^(?:eve|day|week|fast|fasting|sunday|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|lent|holy week|pascha|easter)\b",
    re.IGNORECASE,
)
_RELIGIOUS_TERMS = frozenset({
    "saint", "martyr", "bishop", "patriarch", "apostle", "pope", "priest",
    "monk", "nun", "virgin", "confessor", "deacon", "church", "christian",
    "blessed", "venerable", "holy", "orthodox", "byzantine", "coptic",
    "catholic", "theologian", "abbot", "abbess", "hermit", "ascetic",
})
_WEAK_WORDS = frozenset({
    "thomas", "james", "simon", "peter", "mark", "john", "paul", "stephen",
    "michael", "george", "mary", "andrew", "philip", "matthew", "joseph",
    "cross", "relic", "holy", "feast", "companions", "martyrs", "saints",
})


def _api_get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _extract_text(page: dict) -> str | None:
    if page.get("missing") is not None:
        return None
    raw = (page.get("extract") or "").strip()
    if len(raw) < 30:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    return " ".join(sentences[:3])[:400].strip()


def _is_religious(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in _RELIGIOUS_TERMS)


def fetch_extracts(titles: list[str], delay: float) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
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
        norm: dict[str, str] = {}
        for r in (data.get("query", {}).get("redirects", [])
                  + data.get("query", {}).get("normalized", [])):
            norm[r["from"]] = r["to"]
        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            desc = _extract_text(page)
            if not desc:
                continue
            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            result[title] = {"description": desc, "url": url}
        for orig in batch:
            resolved = norm.get(orig, orig)
            if resolved in result and orig not in result:
                result[orig] = result[resolved]
        if i + 50 < len(titles):
            time.sleep(delay)
    return result


def _search_term(name: str) -> str:
    term = _NAME_PREFIXES.sub("", name).strip()
    term = re.sub(r"^(?:the\s+holy\s+|the\s+blessed\s+|the\s+)", "", term, flags=re.IGNORECASE).strip()
    return term


def _title_relevant(term: str, title: str) -> bool:
    title_lower = title.lower()
    words = [w for w in re.split(r"\W+", term.lower()) if len(w) > 4]
    if not words:
        return False
    strong = [w for w in words if w not in _WEAK_WORDS and w in title_lower]
    weak = [w for w in words if w in _WEAK_WORDS and w in title_lower]
    return bool(strong) or len(weak) >= 2


def search_enrich(names: list[str], delay: float) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for name in names:
        term = _search_term(name)
        if not term or len(term) < 5 or _PURE_LITURGICAL_RE.match(term):
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
            time.sleep(delay)
            continue

        matched_title = None
        for hit in hits:
            title = hit["title"]
            if "disambiguation" in title.lower():
                continue
            if not _title_relevant(term, title):
                continue
            matched_title = title
            break

        if not matched_title:
            time.sleep(delay)
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
            for page in data2.get("query", {}).get("pages", {}).values():
                desc = _extract_text(page)
                if desc and _is_religious(desc):
                    title_out = page.get("title", matched_title)
                    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
                        title_out.replace(" ", "_")
                    )
                    result[name] = {"description": desc, "url": url}
                    break
        except Exception:
            pass

        time.sleep(delay)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich any tradition JSON with Wikipedia data")
    parser.add_argument("--input", required=True, help="Path to tradition JSON file to enrich")
    parser.add_argument("--out", default=None,
                        help="Output path (default: overwrite --input)")
    parser.add_argument("--force-notes", action="store_true",
                        help="Overwrite existing notes (default: only fill empty notes)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be enriched, write nothing")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between Wikipedia API calls (default 0.5)")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.out) if args.out else in_path

    with in_path.open(encoding="utf-8") as f:
        data: list[dict] = json.load(f)

    # Collect saints needing enrichment
    needs_url: list[tuple[dict, str]] = []   # (saint_dict, search_name)
    for entry in data:
        for saint in entry.get("saints", []):
            missing_url = not saint.get("hagiography_url")
            missing_notes = not saint.get("notes") or args.force_notes
            if missing_url or missing_notes:
                name = saint.get("title") or saint.get("name", "")
                if name and not _PURE_LITURGICAL_RE.match(name):
                    needs_url.append((saint, name))

    print(f"Saints needing enrichment: {len(needs_url)}", file=sys.stderr)

    if args.dry_run:
        for _, name in needs_url:
            print(f"  {name}")
        return

    # Pass 1: direct title fetch (fast batch)
    names = list({name for _, name in needs_url})
    print(f"Pass 1: direct fetch for {len(names)} names...", file=sys.stderr)
    enrichment = fetch_extracts(names, args.delay)
    hit1 = len(enrichment)
    print(f"  Got {hit1} descriptions", file=sys.stderr)

    # Pass 2: search for remaining
    unenriched_names = [n for n in names if n not in enrichment]
    print(f"Pass 2: search for {len(unenriched_names)} unenriched...", file=sys.stderr)
    enrichment.update(search_enrich(unenriched_names, args.delay))
    hit2 = len(enrichment) - hit1
    print(f"  Got {hit2} additional descriptions", file=sys.stderr)

    # Apply enrichment to saints
    updated = 0
    for saint, name in needs_url:
        enrich = enrichment.get(name)
        if not enrich:
            continue
        if not saint.get("hagiography_url"):
            saint["hagiography_url"] = enrich["url"]
            updated += 1
        if not saint.get("notes") or args.force_notes:
            saint["notes"] = enrich["description"]

    print(f"Applied enrichment to {updated} saints", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
