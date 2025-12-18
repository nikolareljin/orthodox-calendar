from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from .config import TRADITIONS
from .models import CalendarSystem, Tradition

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
        converted = day - timedelta(days=julian_gregorian_delta(day))
    else:
        converted = day

    return converted.strftime("%m-%d"), converted


def julian_gregorian_delta(day: date) -> int:
    """
    Number of days to shift between Julian and Gregorian on the given civil date.
    Follows the standard formula: delta = century - leap_century - 2, applied
    to the year that owns March 1 for the comparison.
    """
    year = day.year
    if day.month < 3:
        year -= 1
    return year // 100 - year // 400 - 2


def julian_to_gregorian(julian_date: date) -> date:
    """
    Convert a Julian calendar date (passed as a proleptic date object) to a
    Gregorian civil date using the year-appropriate delta.
    """
    return julian_date + timedelta(days=julian_gregorian_delta(julian_date))


def orthodox_pascha(year: int) -> Tuple[date, date, int]:
    """
    Compute Orthodox Pascha using the Julian Paschalion.
    Returns (pascha_julian, pascha_gregorian, indiction_number).
    - Pascha is calculated on the Julian calendar, then converted to Gregorian.
    - Indiction is the 15-year cycle used in Byzantine chronology.
    """
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1

    pascha_julian = date(year, month, day)
    pascha_gregorian = julian_to_gregorian(pascha_julian)
    indiction = ((year + 3) % 15) + 1
    return pascha_julian, pascha_gregorian, indiction
