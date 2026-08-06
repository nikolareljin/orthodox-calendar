#!/usr/bin/env python3
"""
Enrich greek_saints.json with hagiography URLs and notes from oca_julian.json.

The Greek tradition uses the Revised Julian (New Calendar) and the OCA dataset
uses the Julian (Old Calendar), but both traditions share the same NOMINAL
month-day for each fixed feast (e.g. June 20 in both calendars), differing
only in the civil date on which that day falls.  No date offset is needed.

  Greek Revised-Julian 06-20 == OCA Julian 06-20 (same saint, different civil dates)

For each Greek saint without a goarch_url or hagiography_url, we:
  1. Find OCA saints on the same nominal month-day
  2. Match names with a suffix-tolerant algorithm that handles Greek/Latin
     variant spellings (Methodios ↔ Methodius, Eustathios ↔ Eustathius, etc.)
  3. Copy hagiography_url, notes, and extended_notes from the matching OCA saint
     so hagiographies are served in-place without hitting oca.org

Usage:
    python3 scripts/enrich_greek_from_oca.py \\
        --greek backend/app/data/traditions/greek_saints.json \\
        --oca   backend/app/data/oca_julian.json \\
        --dry-run

    python3 scripts/enrich_greek_from_oca.py   # apply changes (no --dry-run)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

_HONORIFIC_RE = re.compile(
    r"^(?:(?:saint|st\.|st|venerable|blessed|holy|righteous|new martyr|neomartyr"
    r"|hieromartyr|martyr|great martyr|hierarch|deacon|hierodeacon|presbyter"
    r"|hieromonk|abbot|abbess|monk|nun|prophet|prophetess|apostle|equal.to.apostles?"
    r"|archbishop|patriarch|bishop|metropolitan|forefeast|afterfeast)\s+)+",
    re.IGNORECASE,
)

_DROP_TOKENS = frozenset({
    "saint", "st", "venerable", "blessed", "holy", "hieromartyr", "martyr",
    "new", "neomartyr", "righteous", "wonderworker",
    "of", "the", "in", "and", "at", "from", "to", "a", "an",
    "bishop", "archbishop", "patriarch", "metropolitan", "presbyter",
    "abbot", "abbess", "monk", "nun", "prophet", "apostle",
    "hierarch", "deacon", "hieromonk",
})

# Greek "ios"/"ias" vs Latin "ius"/"ias"/"ias" suffix equivalence:
# Strip final vowel-consonant suffixes that vary between traditions.
_SUFFIX_NORM_RE = re.compile(r"(ios|ius|ios|ias|is|os|us|as)$")


_OCA_AND_PREFIX_RE = re.compile(
    r"^and\s+(?:god[- ]bearing\s+(?:father\s+)?|evangelist\s+|archdeacon\s+"
    r"|righteous\s+|confessor\s+|metropolitan\s+of\s+\w+\s+and\s+\w+\s+)?",
    re.IGNORECASE,
)


def _tokenize(name: str) -> list[str]:
    """Return normalized, lowercased tokens for a saint name."""
    name = name.lower()
    # Strip prefixes iteratively: OCA may have "Venerable and God-bearing Father …"
    # where _HONORIFIC_RE strips "Venerable " first, exposing "and God-bearing …"
    # which _OCA_AND_PREFIX_RE then strips on the next pass.
    for _ in range(3):
        prev = name
        name = _OCA_AND_PREFIX_RE.sub("", name)
        name = _HONORIFIC_RE.sub("", name)
        if name == prev:
            break
    # Remove punctuation
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    # Remove drop tokens and short tokens
    tokens = [t for t in name.split() if t not in _DROP_TOKENS and len(t) >= 3]
    return tokens


def _stem(token: str) -> str:
    """Normalize variant suffixes: 'methodios' → 'method', 'methodius' → 'method'."""
    return _SUFFIX_NORM_RE.sub("", token)


def _match_score(greek_name: str, oca_name: str) -> float:
    """Return a similarity score in [0, 1] between two saint names.

    Scoring:
      - Primary name token (first significant token) must stem-match.
        If it doesn't, score = 0.
      - Additional tokens add up to 0.5 via Jaccard similarity.
    """
    g_tokens = _tokenize(greek_name)
    o_tokens = _tokenize(oca_name)
    if not g_tokens or not o_tokens:
        return 0.0

    # Primary name token must match (after suffix normalization)
    g_primary = _stem(g_tokens[0])
    o_primary = _stem(o_tokens[0])

    # Accept if stems match exactly OR one contains the other (min length 4)
    if g_primary == o_primary:
        primary_match = True
    elif len(g_primary) >= 4 and len(o_primary) >= 4:
        primary_match = g_primary in o_primary or o_primary in g_primary
    else:
        primary_match = False

    if not primary_match:
        return 0.0

    # Jaccard similarity on stemmed secondary tokens
    g_stems = {_stem(t) for t in g_tokens[1:]}
    o_stems = {_stem(t) for t in o_tokens[1:]}
    if g_stems or o_stems:
        intersection = len(g_stems & o_stems)
        union = len(g_stems | o_stems)
        secondary_score = intersection / union if union else 0.5
    else:
        secondary_score = 0.5

    return 0.5 + secondary_score * 0.5


# ---------------------------------------------------------------------------
# Main enrichment logic
# ---------------------------------------------------------------------------

def enrich(greek_path: Path, oca_path: Path, dry_run: bool = False) -> None:
    greek = json.loads(greek_path.read_text())
    oca = json.loads(oca_path.read_text())

    # Index OCA by month_day for fast lookup.
    # Both Revised Julian (Greek) and Julian (OCA) share the same nominal month-day
    # for fixed feasts — e.g. Greek Revised-Julian 06-20 == OCA Julian 06-20 (same
    # saints, different civil dates). No offset conversion is needed.
    oca_by_md: dict[str, list[dict]] = {}
    for entry in oca:
        oca_by_md.setdefault(entry["month_day"], []).append(entry)

    def oca_saints_for_md(month_day: str) -> list[dict]:
        """Return OCA saints on the same nominal month-day."""
        candidates = []
        for oca_entry in oca_by_md.get(month_day, []):
            candidates.extend(oca_entry["saints"])
        return candidates

    matched = 0
    skipped_has_url = 0
    total = 0

    for day_entry in greek:
        md = day_entry["month_day"]
        oca_saints = oca_saints_for_md(md)

        # Pre-compute how many OCA saints on this date share each primary name token.
        # If a name like "Gregory" or "Anthony" appears 3+ times on the same date,
        # a score-0.50 match (primary name only) is likely a false positive.
        oca_primary_counts: dict[str, int] = {}
        for oca_s in oca_saints:
            o_tokens = _tokenize(oca_s.get("title") or oca_s.get("name") or "")
            if o_tokens:
                key = _stem(o_tokens[0])
                oca_primary_counts[key] = oca_primary_counts.get(key, 0) + 1

        for saint in day_entry["saints"]:
            total += 1
            # Skip if already has GOARCH or hagiography URL
            if saint.get("goarch_url") or saint.get("hagiography_url"):
                skipped_has_url += 1
                continue

            g_name = saint.get("title") or saint.get("name") or ""
            if not g_name:
                continue

            # Find best matching OCA saint
            best_score = 0.0
            best_oca: dict | None = None
            for oca_s in oca_saints:
                o_name = oca_s.get("title") or oca_s.get("name") or ""
                score = _match_score(g_name, o_name)
                if score > best_score:
                    best_score = score
                    best_oca = oca_s

            # Penalize ambiguous primary-name-only matches:
            # if 2+ OCA saints share the same primary name stem on this date
            # and the score is exactly 0.5 (no secondary confirmation), skip.
            if best_score == 0.5:
                g_tokens = _tokenize(g_name)
                if g_tokens:
                    g_primary_stem = _stem(g_tokens[0])
                    if oca_primary_counts.get(g_primary_stem, 0) > 1:
                        continue  # ambiguous — multiple candidates, no secondary match

            # Accept match at score ≥ 0.5 (primary name must match)
            if best_oca and best_score >= 0.5:
                if dry_run:
                    o_name = best_oca.get("title") or best_oca.get("name") or ""
                    print(f"  {md} ({best_score:.2f}) '{g_name[:45]}'  →  '{o_name[:45]}'")
                else:
                    if best_oca.get("hagiography_url"):
                        saint["hagiography_url"] = best_oca["hagiography_url"]
                    oca_notes = best_oca.get("notes") or ""
                    if oca_notes:
                        if not saint.get("notes"):
                            saint["notes"] = oca_notes[:300]
                        # Store the full text in-place as extended_notes so the
                        # /hagiography endpoint can serve it without hitting OCA.
                        if not saint.get("extended_notes"):
                            saint["extended_notes"] = oca_notes
                matched += 1

    unmatched = total - skipped_has_url - matched
    print(f"Total saints: {total}", file=sys.stderr)
    print(f"Already have URL: {skipped_has_url}", file=sys.stderr)
    print(f"Matched via OCA: {matched}", file=sys.stderr)
    print(f"Still unmatched: {unmatched}", file=sys.stderr)

    if not dry_run:
        greek_path.write_text(json.dumps(greek, ensure_ascii=False, indent=2))
        print(f"Wrote → {greek_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich Greek saints with OCA hagiography data")
    parser.add_argument("--greek", default="backend/app/data/traditions/greek_saints.json")
    parser.add_argument("--oca", default="backend/app/data/oca_julian.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=0.5)
    args = parser.parse_args()

    enrich(Path(args.greek), Path(args.oca), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
