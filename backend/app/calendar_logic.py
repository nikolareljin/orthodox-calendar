from __future__ import annotations

import math as _math
from datetime import date, timedelta
from datetime import date as _date
from typing import Optional, Tuple

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


# Fallback for Revised Julian (Milankovich/New Calendar) traditions if a deployment
# adds one without specifying its own adoption date. Built-in traditions set this
# per church.
_DEFAULT_REVISED_JULIAN_REFORM_DATE = date(1923, 10, 14)
_REVISED_ALIGNMENT_DATE = date(1923, 10, 14)
_MONTH_DAYS_COMMON = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_DAYS_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def effective_calendar(day: date, tradition: Tradition) -> CalendarSystem:
    """Return the calendar system actually in use for this tradition on this date."""
    if tradition.calendar == CalendarSystem.JULIAN:
        return CalendarSystem.JULIAN
    if tradition.calendar != CalendarSystem.REVISED:
        return tradition.calendar

    reform_date = tradition.reform_date or _DEFAULT_REVISED_JULIAN_REFORM_DATE
    return CalendarSystem.REVISED if day >= reform_date else CalendarSystem.JULIAN


def convert_to_tradition_month_day(day: date, tradition: Tradition) -> Tuple[str, str]:
    """
    Convert a civil (Gregorian) date to the month-day string used by the
    tradition's calendar. Returns (MM-DD, YYYY-MM-DD as string).
    """
    calendar = effective_calendar(day, tradition)
    if calendar == CalendarSystem.JULIAN:
        jyear, jmonth, jday = _gregorian_to_julian(day)
        return f"{jmonth:02d}-{jday:02d}", f"{jyear:04d}-{jmonth:02d}-{jday:02d}"
    if calendar == CalendarSystem.REVISED:
        ryear, rmonth, rday = _gregorian_to_revised_julian(day)
        return f"{rmonth:02d}-{rday:02d}", f"{ryear:04d}-{rmonth:02d}-{rday:02d}"
    if calendar == CalendarSystem.COPTIC:
        cy, cm, cd = _gregorian_to_alexandrian(day, 283)
        return day.strftime("%m-%d"), f"{cy:04d}-{cm:02d}-{cd:02d}"
    if calendar == CalendarSystem.ETHIOPIAN:
        ey, em, ed = _gregorian_to_alexandrian(day, 7)
        return day.strftime("%m-%d"), f"{ey:04d}-{em:02d}-{ed:02d}"
    return day.strftime("%m-%d"), day.isoformat()  # Gregorian pass-through


def _is_gregorian_leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _gregorian_to_alexandrian(d: date, year_offset: int) -> Tuple[int, int, int]:
    """Convert a Gregorian date to an Alexandrian-family calendar (Coptic or Ethiopian).

    year_offset: years to subtract from Gregorian year — 283 for Coptic (AM), 7 for Ethiopian (AM).
    Both calendars share 12×30-day months + a short 13th month (5 or 6 days in leap year).
    New Year (1 Thout / 1 Meskerem) = September 11 normally, September 12 if next year is a leap year.
    """
    # New Year day for the Gregorian year in which this date falls
    ny_day = 12 if _is_gregorian_leap(d.year + 1) else 11
    is_after_ny = d.month > 9 or (d.month == 9 and d.day >= ny_day)
    trad_year = (d.year - year_offset) if is_after_ny else (d.year - year_offset - 1)

    # New Year date for the traditional year in question
    ny_g_year = d.year if is_after_ny else d.year - 1
    ny_day_for_year = 12 if _is_gregorian_leap(ny_g_year + 1) else 11
    ny_date = date(ny_g_year, 9, ny_day_for_year)

    days_since_ny = (d - ny_date).days
    month = min(12, days_since_ny // 30) + 1  # months 1-12 are 30 days; 13th is remainder
    day_in_month = (days_since_ny % 30) + 1
    if month == 13:
        max_day = 6 if trad_year % 4 == 3 else 5  # 13th month: 6 days in leap year
        day_in_month = min(day_in_month, max_day)
    return trad_year, month, day_in_month


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


def _gregorian_to_revised_julian(d: date) -> Tuple[int, int, int]:
    """Convert Gregorian date to Revised Julian (Milankovich) calendar date."""
    jdn = _gregorian_jdn(d)
    alignment_jdn = _gregorian_jdn(_REVISED_ALIGNMENT_DATE)
    alignment_ordinal = _revised_julian_ordinal(
        _REVISED_ALIGNMENT_DATE.year,
        _REVISED_ALIGNMENT_DATE.month,
        _REVISED_ALIGNMENT_DATE.day,
    )
    return _revised_julian_from_ordinal(alignment_ordinal + (jdn - alignment_jdn))


def _gregorian_jdn(d: date) -> int:
    """Return the Julian Day Number for a Gregorian date."""
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _revised_julian_leap_year(year: int) -> bool:
    """Return true for leap years under Milankovich's 900-year rule."""
    if year % 4 != 0:
        return False
    if year % 100 != 0:
        return True
    return year % 900 in (200, 600)


def _revised_julian_leaps_before(year: int) -> int:
    years = year - 1
    restored_century_leaps = sum(
        ((years - remainder) // 900 + 1) if years >= remainder else 0
        for remainder in (200, 600)
    )
    return years // 4 - years // 100 + restored_century_leaps


def _revised_julian_ordinal(year: int, month: int, day: int) -> int:
    month_days = _MONTH_DAYS_LEAP if _revised_julian_leap_year(year) else _MONTH_DAYS_COMMON
    return (
        365 * (year - 1)
        + _revised_julian_leaps_before(year)
        + sum(month_days[: month - 1])
        + day
    )


def _revised_julian_from_ordinal(ordinal: int) -> Tuple[int, int, int]:
    low, high = 1, 10000
    while _revised_julian_ordinal(high, 12, 31) < ordinal:
        high *= 2

    while low < high:
        mid = (low + high) // 2
        if _revised_julian_ordinal(mid + 1, 1, 1) <= ordinal:
            low = mid + 1
        else:
            high = mid

    year = low
    day_of_year = ordinal - _revised_julian_ordinal(year, 1, 1) + 1
    month_days = _MONTH_DAYS_LEAP if _revised_julian_leap_year(year) else _MONTH_DAYS_COMMON
    month = 1
    for days_in_month in month_days:
        if day_of_year <= days_in_month:
            return year, month, day_of_year
        day_of_year -= days_in_month
        month += 1
    raise ValueError(f"Invalid Revised Julian ordinal: {ordinal}")


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


# ---------------------------------------------------------------------------
# Movable feast support
# ---------------------------------------------------------------------------

# Pascha-relative day offsets → (canonical key, display title, feast_type).
# These cover the major Byzantine movable feasts computed from the Julian computus.
_PASCHA_OFFSETS: dict[int, tuple[str, str, str]] = {
    -48: ("clean_monday",       "Beginning of Great Lent (Clean Monday)",                     "Great Feast"),
    -8:  ("lazarus_saturday",   "The Raising of Lazarus (Lazarus Saturday)",                   "Great Feast"),
    -7:  ("palm_sunday",        "Entry of Our Lord into Jerusalem (Palm Sunday)",              "Great Feast"),
    -3:  ("holy_thursday",      "Great and Holy Thursday",                                     "Great Feast"),
    -2:  ("holy_friday",        "Great and Holy Friday",                                       "Great Feast"),
    -1:  ("holy_saturday",      "Great and Holy Saturday",                                     "Great Feast"),
     0:  ("pascha",             "HOLY PASCHA: The Resurrection of Our Lord",                   "Great Feast"),
     1:  ("bright_monday",      "Bright Monday",                                               "Great Feast"),
     7:  ("thomas_sunday",      "Antipascha: Saint Thomas Sunday",                             "Great Feast"),
    24:  ("mid_pentecost",      "Midfeast of Pentecost",                                       "Great Feast"),
    39:  ("ascension",          "The Ascension of our Lord, God and Savior Jesus Christ",      "Great Feast"),
    49:  ("pentecost",          "Holy Pentecost (Trinity Sunday)",                             "Great Feast"),
    56:  ("all_saints",         "Synaxis of All Saints",                                       "Great Feast"),
    57:  ("apostles_fast",      "Beginning of the Apostles' Fast",                             "Minor Feast"),
}

# Title substrings (lower-cased) that identify a movable feast saint in the
# static OCA dataset.  Those entries were scraped at 2024 Gregorian dates and
# are wrong for every other year; they are filtered out and re-injected by
# movable_feast_for_date() instead.
_MOVABLE_FEAST_KEYWORDS: frozenset[str] = frozenset({
    # Pascha and Holy Week
    "holy pascha",
    "great and holy thursday",
    "great and holy friday",
    "great and holy saturday",
    "lazarus saturday",
    "entry of our lord into jerusalem",
    # Bright Week (week after Pascha)
    "bright monday",
    "bright tuesday",
    "bright wednesday",
    "bright friday",
    "bright saturday",
    # Post-Paschal feasts
    "antipascha",
    "midfeast of pentecost",
    "ascension of our lord",
    "holy pentecost",
    "postfeast of pentecost",
    "day of the holy spirit",
    "synaxis of all saints",
    "beginning of the apostles",
    # Pre-Lent and Great Lent
    "beginning of great lent",
    "sunday of the publican",
    "saturday of great lent",
    "sunday of great lent",
    "sunday of orthodoxy",
    "meatfare",
    "cheesefare",
})


def is_movable_feast_title(title: str) -> bool:
    """Return True when *title* belongs to a Pascha-relative movable feast."""
    tl = (title or "").lower()
    return any(kw in tl for kw in _MOVABLE_FEAST_KEYWORDS)


def movable_feast_for_date(day: _date) -> Optional[tuple[str, str, str]]:
    """Return (key, title, feast_type) if *day* (Gregorian) is a movable feast, else None.

    Uses the Julian computus; applies to all Eastern Orthodox traditions
    (Julian and Revised Julian alike) since both use the same Pascha calculation.
    """
    pascha = julian_pascha_as_gregorian(day.year)
    delta = (day - pascha).days
    return _PASCHA_OFFSETS.get(delta)


def movable_feasts(year: int, pascha: "_date | None" = None) -> dict:
    """
    Return a dict of movable feast names -> Gregorian dates for Eastern Orthodoxy.
    All traditions share the same movable feast schedule (Julian computus).
    Pass a precomputed *pascha* date to avoid recomputing it.
    """
    if pascha is None:
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
