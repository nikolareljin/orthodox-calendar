from __future__ import annotations

from datetime import date, timedelta
from typing import List
from uuid import uuid4

from ..calendar_logic import canonical_tradition_key
from ..services.saints import get_saints_for_date


def generate_ical_feed(tradition: str, start: date, days: int = 365) -> str:
    canonical = canonical_tradition_key(tradition)
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//orthodox-calendar//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:orthodox-calendar ({canonical})",
    ]

    for i in range(days):
        target_date = start + timedelta(days=i)
        entries = get_saints_for_date(target_date, [canonical])
        for entry in entries:
            for saint in entry.saints:
                uid = uuid4()
                lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"UID:{uid}@orthodox-calendar",
                        f"SUMMARY:{saint.title or saint.name}",
                        f"DTSTART;VALUE=DATE:{target_date.strftime('%Y%m%d')}",
                        f"DTEND;VALUE=DATE:{(target_date + timedelta(days=1)).strftime('%Y%m%d')}",
                        f"DESCRIPTION:{saint.hagiography_url or ''}",
                        f"CATEGORIES:{entry.tradition}",
                        "END:VEVENT",
                    ]
                )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

