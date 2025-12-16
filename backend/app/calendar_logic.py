from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from .config import TRADITIONS
from .models import CalendarSystem, Tradition

JULIAN_OFFSET_DAYS = 13  # current delta between Julian and Gregorian calendars


def resolve_tradition(name: str) -> Tradition:
    key = name.lower()
    if key in TRADITIONS:
        return TRADITIONS[key]

    for tradition in TRADITIONS.values():
        if key == tradition.name.lower() or key in tradition.aliases:
            return tradition
    raise ValueError(f"Unknown tradition '{name}'.")


def canonical_tradition_key(name: str) -> str:
    key = name.lower()
    if key in TRADITIONS:
        return key

    for canonical, tradition in TRADITIONS.items():
        if key == tradition.name.lower() or key in tradition.aliases:
            return canonical
    raise ValueError(f"Unknown tradition '{name}'.")


def convert_to_tradition_month_day(day: date, tradition: Tradition) -> Tuple[str, date]:
    """
    Convert a civil (Gregorian) date to the month-day string used by the
    tradition's calendar. Returns (MM-DD, converted_date).
    """
    if tradition.calendar == CalendarSystem.JULIAN:
        converted = day - timedelta(days=JULIAN_OFFSET_DAYS)
    else:
        converted = day

    return converted.strftime("%m-%d"), converted
