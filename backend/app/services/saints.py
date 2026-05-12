from __future__ import annotations

from datetime import date
from typing import List

from ..calendar_logic import canonical_tradition_key, convert_to_tradition_month_day, resolve_tradition
from ..data_loader import build_index
from ..models import SaintsResponse

_INDEX = build_index()


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

        # Merge saints from all entries, dedup by name
        seen: set = set()
        merged: List = []
        merged_notes = None
        for entry in day_entries:
            for saint in entry.saints:
                key = saint.name.lower().strip()
                if key not in seen:
                    merged.append(saint)
                    seen.add(key)
            if entry.notes and not merged_notes:
                merged_notes = entry.notes

        responses.append(
            SaintsResponse(
                date=day,
                tradition=tradition.name,
                calendar_date=calendar_date.strftime("%Y-%m-%d"),
                saints=merged,
                calendar_system=tradition.calendar,
                notes=merged_notes,
            )
        )
    return responses

