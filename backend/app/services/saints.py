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


def _saint_key(saint: Saint) -> str:
    """Stable dedup key: normalized name with honorific prefixes stripped.

    Different sources prefix the same saint differently (e.g. "Seraphim of
    Sarov" vs "Saint Seraphim of Sarov"). Stripping known prefixes before
    keying lets overlays merge correctly instead of producing duplicates.
    """
    name = saint.name.lower().strip()
    return _HONORIFIC_RE.sub("", name)


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

        # Merge saints from all entries; dedup by normalized name (honorifics
        # stripped). Overlay entries enrich base canonization fields rather
        # than being skipped entirely.
        merged: Dict[str, Saint] = {}
        merged_notes: Optional[str] = None
        for entry in day_entries:
            for saint in entry.saints:
                key = _saint_key(saint)
                if key in merged:
                    _apply_overlay(merged[key], saint)
                else:
                    merged[key] = saint.model_copy()
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
