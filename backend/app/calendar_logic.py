from __future__ import annotations

import math as _math
from datetime import date, timedelta
from datetime import date as _date
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


def convert_to_tradition_month_day(day: date, tradition: Tradition) -> Tuple[str, str]:
    """
    Convert a civil (Gregorian) date to the month-day string used by the
    tradition's calendar. Returns (MM-DD, YYYY-MM-DD as string).
    """
    if tradition.calendar == CalendarSystem.JULIAN:
        jyear, jmonth, jday = _gregorian_to_julian(day)
        return f"{jmonth:02d}-{jday:02d}", f"{jyear:04d}-{jmonth:02d}-{jday:02d}"
    return day.strftime("%m-%d"), day.isoformat()


def _gregorian_to_julian(d: date) -> Tuple[int, int, int]:
    """Convert Gregorian date to Julian calendar date via Julian Day Number.

    Returns (year, month, day) as integers to avoid Gregorian validation of
    Julian leap days (e.g. Julian Feb 29 in century years like 2100).
    """
    # Gregorian JDN
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    jdn = d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    # JDN to Julian calendar
    c = jdn + 32082
    d4 = (4 * c + 3) // 1461
    e4 = c - (1461 * d4) // 4
    m4 = (5 * e4 + 2) // 153
    jday = e4 - (153 * m4 + 2) // 5 + 1
    jmonth = m4 + 3 - 12 * (m4 // 10)
    jyear = d4 - 4800 + m4 // 10
    return jyear, jmonth, jday


def julian_pascha_as_gregorian(year: int) -> _date:
    """
    Compute Eastern Pascha (Easter) for the given year using the Julian computus,
    returned as a proleptic Gregorian calendar date.
    Supported range: years 1–9999 (Python datetime.date constraint).
    """
    # Julian Easter (Meeus algorithm)
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    julian_month = (d + e + 114) // 31
    julian_day = (d + e + 114) % 31 + 1
    return _julian_to_gregorian(year, julian_month, julian_day)


def _julian_to_gregorian(year: int, month: int, day: int) -> _date:
    """Convert a proleptic Julian calendar date to proleptic Gregorian via JDN."""
    # Julian Day Number from Julian calendar
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    # JDN to Gregorian
    a4 = jdn + 32044
    b4 = (4 * a4 + 3) // 146097
    c4 = a4 - (146097 * b4) // 4
    d4 = (4 * c4 + 3) // 1461
    e4 = c4 - (1461 * d4) // 4
    m4 = (5 * e4 + 2) // 153
    gday = e4 - (153 * m4 + 2) // 5 + 1
    gmonth = m4 + 3 - 12 * (m4 // 10)
    gyear = 100 * b4 + d4 - 4800 + m4 // 10
    return _date(gyear, gmonth, gday)


def movable_feasts(year: int) -> dict:
    """
    Return a dict of movable feast names -> Gregorian dates for Eastern Orthodoxy.
    All traditions share the same movable feast schedule (Julian computus).
    """
    pascha = julian_pascha_as_gregorian(year)
    return {
        "great_lent_start": (pascha - timedelta(days=48)).isoformat(),
        "lazarus_saturday": (pascha - timedelta(days=8)).isoformat(),
        "palm_sunday": (pascha - timedelta(days=7)).isoformat(),
        "holy_thursday": (pascha - timedelta(days=3)).isoformat(),
        "holy_friday": (pascha - timedelta(days=2)).isoformat(),
        "holy_saturday": (pascha - timedelta(days=1)).isoformat(),
        "pascha": pascha.isoformat(),
        "bright_monday": (pascha + timedelta(days=1)).isoformat(),
        "thomas_sunday": (pascha + timedelta(days=7)).isoformat(),
        "mid_pentecost": (pascha + timedelta(days=24)).isoformat(),
        "ascension": (pascha + timedelta(days=39)).isoformat(),
        "pentecost": (pascha + timedelta(days=49)).isoformat(),
        "all_saints": (pascha + timedelta(days=56)).isoformat(),
        "apostles_fast_start": (pascha + timedelta(days=57)).isoformat(),
    }


def moon_phase(d: "date") -> dict:
    """Return lunar phase info for a given date."""
    from datetime import date as _d2
    # Known new moon: January 6, 2000 (Gregorian)
    reference = _d2(2000, 1, 6)
    synodic = 29.53058867  # days
    delta = (d - reference).days
    phase = (delta % synodic) / synodic

    illumination = (1 - _math.cos(2 * _math.pi * phase)) / 2

    if phase < 0.0625 or phase >= 0.9375:
        name, emoji = "New Moon", "🌑"
    elif phase < 0.1875:
        name, emoji = "Waxing Crescent", "🌒"
    elif phase < 0.3125:
        name, emoji = "First Quarter", "🌓"
    elif phase < 0.4375:
        name, emoji = "Waxing Gibbous", "🌔"
    elif phase < 0.5625:
        name, emoji = "Full Moon", "🌕"
    elif phase < 0.6875:
        name, emoji = "Waning Gibbous", "🌖"
    elif phase < 0.8125:
        name, emoji = "Last Quarter", "🌗"
    else:
        name, emoji = "Waning Crescent", "🌘"

    return {
        "phase": round(phase, 4),
        "phase_name": name,
        "emoji": emoji,
        "illumination": round(illumination, 4),
    }
