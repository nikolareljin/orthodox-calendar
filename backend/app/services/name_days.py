from __future__ import annotations

import re
from datetime import date
from typing import List

from ..models import Contact, NameDayMatch, NameDayResponse, Saint
from .saints import get_saints_for_date


def _normalize_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z]", " ", text)
    return cleaned.lower().strip().split(" ")[0] if cleaned.strip() else ""


def find_name_days(day: date, traditions: List[str], contacts: List[Contact]) -> NameDayResponse:
    saints_by_tradition = get_saints_for_date(day, traditions)
    matches: List[NameDayMatch] = []

    for contact in contacts:
        first_name = _normalize_name(contact.full_name)
        if not first_name:
            continue

        for entry in saints_by_tradition:
            for saint in entry.saints:
                saint_key = _normalize_name(saint.name)
                if not saint_key:
                    continue
                if first_name == saint_key:
                    matches.append(
                        NameDayMatch(
                            contact=contact,
                            saint=saint,
                            tradition=entry.tradition,
                            date=day,
                            calendar_system=entry.calendar_system,
                        )
                    )

    return NameDayResponse(matches=matches, checked_date=day)

