#!/usr/bin/env python3
"""Calculate Eastern Orthodox Pascha (Easter) and all related movable feasts.

Usage:
    python3 scripts/pascha.py          # current year
    python3 scripts/pascha.py 2026     # specific year
    python3 scripts/pascha.py 2025 2030  # year range

Note: the Julian→Gregorian conversion and Pascha computus here duplicate
backend/app/calendar_logic.py intentionally.  This script is a standalone CLI
tool used outside the Python package (e.g. during data import or from a bare
checkout with no venv), so it avoids importing from the backend package.
"""

import sys
from datetime import date, timedelta


def _julian_to_gregorian(year: int, month: int, day: int) -> date:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    a4 = jdn + 32044
    b4 = (4 * a4 + 3) // 146097
    c4 = a4 - (146097 * b4) // 4
    d4 = (4 * c4 + 3) // 1461
    e4 = c4 - (1461 * d4) // 4
    m4 = (5 * e4 + 2) // 153
    gday   = e4 - (153 * m4 + 2) // 5 + 1
    gmonth = m4 + 3 - 12 * (m4 // 10)
    gyear  = 100 * b4 + d4 - 4800 + m4 // 10
    return date(gyear, gmonth, gday)


def pascha(year: int) -> date:
    """Julian computus (Meeus algorithm) → Gregorian date."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    julian_month = (d + e + 114) // 31
    julian_day   = (d + e + 114) % 31 + 1
    return _julian_to_gregorian(year, julian_month, julian_day)


FEASTS = [
    # Pre-Triodion Sunday
    (-77, "Sunday of Zacchaeus"),
    # Pre-Lent Triodion
    (-70, "Sunday of the Publican and the Pharisee"),
    (-63, "Sunday of the Prodigal Son"),
    (-57, "Soul Saturday of Meatfare Week"),
    (-56, "Meatfare Sunday (Sunday of Last Judgment)"),
    (-50, "Cheesefare Saturday"),
    (-49, "Cheesefare Sunday (Forgiveness Sunday)"),
    # Great Lent
    (-48, "Clean Monday — Great Lent begins"),
    (-43, "1st Saturday of Great Lent (Soul Saturday)"),
    (-42, "1st Sunday of Great Lent (Sunday of Orthodoxy)"),
    (-36, "2nd Saturday of Great Lent (Soul Saturday)"),
    (-35, "2nd Sunday of Great Lent (St Gregory Palamas)"),
    (-29, "3rd Saturday of Great Lent"),
    (-28, "3rd Sunday of Great Lent (Veneration of Holy Cross)"),
    (-22, "4th Saturday of Great Lent (Akathist Saturday)"),
    (-21, "4th Sunday of Great Lent (St John Climacus)"),
    (-15, "5th Saturday of Great Lent"),
    (-14, "5th Sunday of Great Lent (St Mary of Egypt)"),
    # Holy Week
    ( -8, "Lazarus Saturday"),
    ( -7, "Palm Sunday"),
    ( -6, "Great and Holy Monday"),
    ( -5, "Great and Holy Tuesday"),
    ( -4, "Great and Holy Wednesday"),
    ( -3, "Holy Thursday"),
    ( -2, "Holy Friday"),
    ( -1, "Holy Saturday"),
    # Pascha and Bright Week
    (  0, "HOLY PASCHA — The Resurrection of Our Lord"),
    (  1, "Bright Monday"),
    (  2, "Bright Tuesday"),
    (  3, "Bright Wednesday"),
    (  4, "Bright Thursday"),
    (  5, "Bright Friday — Life-Giving Spring of the Theotokos"),
    (  6, "Bright Saturday"),
    (  7, "Thomas Sunday (Antipascha)"),
    # Post-Paschal Sundays
    ( 14, "Sunday of the Holy Myrrhbearing Women"),
    ( 21, "Sunday of the Paralytic"),
    ( 24, "Midfeast of Pentecost"),
    ( 28, "Sunday of the Samaritan Woman"),
    ( 35, "Sunday of the Blind Man"),
    ( 38, "Leavetaking of Pascha"),
    ( 39, "Ascension of Our Lord"),
    ( 48, "Soul Saturday before Pentecost"),
    ( 49, "Holy Pentecost (Trinity Sunday)"),
    ( 56, "All Saints Sunday"),
    ( 57, "Apostles' Fast begins"),
]


def print_year(year: int) -> None:
    p = pascha(year)
    print(f"\n{'═' * 58}")
    print(f"  Orthodox Movable Feasts — {year}")
    print(f"{'═' * 58}")
    for delta, name in FEASTS:
        d = p + timedelta(days=delta)
        marker = " ◄" if delta == 0 else ""
        print(f"  {d.strftime('%b %d')}  {name}{marker}")
    print()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print_year(date.today().year)
    elif len(args) == 1:
        print_year(int(args[0]))
    else:
        start, end = int(args[0]), int(args[1])
        for y in range(start, end + 1):
            print_year(y)


if __name__ == "__main__":
    main()
