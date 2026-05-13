from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from ..calendar_logic import canonical_tradition_key, convert_to_tradition_month_day, effective_calendar, resolve_tradition
from ..data_loader import build_index
from ..models import Saint, SaintsResponse

_INDEX = build_index()


def _saint_key(saint: Saint) -> str:
    """Stable dedup key: normalized name.

    URL-first keying breaks dedup when the same saint appears in multiple
    sources with different (or absent) hagiography URLs. Name is the stable
    cross-source identifier; URL is enriched via _apply_overlay after merge.
    """
    return saint.name.lower().strip()


def _apply_overlay(base: Saint, overlay: Saint) -> None:
    """Merge overlay canonization metadata into base saint in-place.

    Overlay entries carry tradition-specific canonization data that the shared
    base dataset lacks; prefer non-None overlay values for those fields only.
    """
    if overlay.canonized_by and not base.canonized_by:
        base.canonized_by = overlay.canonized_by
    if overlay.canonization_scope and not base.canonization_scope:
        base.canonization_scope = overlay.canonization_scope
    if overlay.year_canonized and not base.year_canonized:
        base.year_canonized = overlay.year_canonized
    if overlay.hagiography_url and not base.hagiography_url:
        base.hagiography_url = overlay.hagiography_url


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

        # Merge saints from all entries; dedup by stable key (hagiography_url
        # or normalized name). Overlay entries enrich base canonization fields
        # rather than being skipped entirely.
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
