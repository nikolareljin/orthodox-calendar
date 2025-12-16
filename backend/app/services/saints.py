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

        entries = [entry for entry in _INDEX.get(canonical, []) if entry.month_day == month_day]
        if not entries:
            continue

        for entry in entries:
            responses.append(
                SaintsResponse(
                    date=day,
                    tradition=tradition.name,
                    calendar_date=calendar_date.strftime("%Y-%m-%d"),
                    saints=entry.saints,
                    calendar_system=tradition.calendar,
                    notes=entry.notes,
                )
            )
    return responses

