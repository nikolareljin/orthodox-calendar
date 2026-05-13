from __future__ import annotations

import re as _re
from datetime import date
from typing import Dict, List, Optional

from ..calendar_logic import canonical_tradition_key, convert_to_tradition_month_day, effective_calendar, resolve_tradition
from ..data_loader import build_index
from ..models import Saint, SaintsResponse

_INDEX = build_index()

# Common honorific prefixes that vary across sources for the same saint
# (e.g. base has "Seraphim of Sarov", overlay has "Saint Seraphim of Sarov").
_HONORIFIC_RE = _re.compile(
    r"^(?:(?:saint|st\.|st|venerable|blessed|holy|new martyr|hieromartyr|martyr)\s+)+",
    _re.IGNORECASE,
)
_EVENT_PREFIX_RE = _re.compile(
    r"^(?:(?:translation|uncovering|discovery|opening) of (?:the )?relics of "
    r"|(?:repose|translation|uncovering|discovery|opening) of (?:the )?)+",
    _re.IGNORECASE,
)
_DROP_TOKENS = {
    "saint",
    "st",
    "venerable",
    "blessed",
    "holy",
    "hieromartyr",
    "martyr",
    "new",
    "righteous",
    "wonderworker",
    "great",
    "of",
    "the",
}


def _normalize_saint_text(value: str) -> str:
    value = _EVENT_PREFIX_RE.sub("", value.lower().strip())
    value = _HONORIFIC_RE.sub("", value)
    value = _re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in _DROP_TOKENS]
    return " ".join(tokens)


def _saint_keys(saint: Saint) -> List[str]:
    """Stable dedup aliases from normalized title, name, and hagiography slug.

    Different sources phrase the same commemoration differently (e.g. "Repose
    of Venerable Seraphim" vs "Seraphim of Sarov"). Multiple aliases let
    overlays merge when any stable representation matches.
    """
    raw_values = [saint.title, saint.name]
    if saint.hagiography_url:
        raw_values.append(saint.hagiography_url.rsplit("/", 1)[-1])

    keys: List[str] = []
    for raw in raw_values:
        if not raw:
            continue
        key = _normalize_saint_text(raw)
        if key and key not in keys:
            keys.append(key)
    return keys or [saint.name.lower().strip()]


def _apply_overlay(base: Saint, overlay: Saint) -> None:
    """Merge overlay fields into base saint in-place.

    Overlay entries carry tradition-specific canonization data and richer
    hagiography fields that the shared base dataset may lack.
    """
    if overlay.title and not base.title:
        base.title = overlay.title
    if overlay.feast_type and not base.feast_type:
        base.feast_type = overlay.feast_type
    if overlay.hagiography_url and not base.hagiography_url:
        base.hagiography_url = overlay.hagiography_url
    if overlay.icon_url and not base.icon_url:
        base.icon_url = overlay.icon_url
    if overlay.notes and not base.notes:
        base.notes = overlay.notes
    if overlay.canonized_by and not base.canonized_by:
        base.canonized_by = overlay.canonized_by
    if overlay.canonization_scope and not base.canonization_scope:
        base.canonization_scope = overlay.canonization_scope
    if overlay.year_canonized and not base.year_canonized:
        base.year_canonized = overlay.year_canonized


def get_saints_for_date(day: date, traditions: List[str]) -> List[SaintsResponse]:
    responses: List[SaintsResponse] = []
    for tradition_name in traditions:
        tradition = resolve_tradition(tradition_name)
        canonical = canonical_tradition_key(tradition_name)
        month_day, calendar_date = convert_to_tradition_month_day(day, tradition)

        base_key = tradition.data_key or canonical
        day_entries = [e for e in _INDEX.get(base_key, []) if e.month_day == month_day]

        # Also include tradition-specific overlay entries
        if tradition.data_key:
            day_entries.extend(
                e for e in _INDEX.get(canonical, []) if e.month_day == month_day
            )

        if not day_entries:
            continue

        # Merge saints from all entries; dedup by normalized aliases from title,
        # name, and hagiography slug. Overlay entries enrich base fields rather
        # than being skipped entirely.
        merged: Dict[str, Saint] = {}
        key_index: Dict[str, str] = {}
        merged_notes: Optional[str] = None
        for entry in day_entries:
            for saint in entry.saints:
                keys = _saint_keys(saint)
                primary_key = next((key_index[key] for key in keys if key in key_index), None)
                if primary_key:
                    _apply_overlay(merged[primary_key], saint)
                    for key in keys:
                        key_index.setdefault(key, primary_key)
                else:
                    primary_key = keys[0]
                    merged[primary_key] = saint.model_copy()
                    for key in keys:
                        key_index[key] = primary_key
            if entry.notes and not merged_notes:
                merged_notes = entry.notes

        responses.append(
            SaintsResponse(
                date=day,
                tradition=tradition.name,
                calendar_date=calendar_date,
                saints=list(merged.values()),
                calendar_system=effective_calendar(day, tradition),
                notes=merged_notes,
            )
        )
    return responses
