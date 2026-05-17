import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from import_malankara import parse_ics, julian_civil_to_malankara


def test_parse_ics_basic():
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20260107\r\n"
        "SUMMARY:Feast of the Nativity of Our Lord\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert result == {"01-07": "Feast of the Nativity of Our Lord"}


def test_parse_ics_keeps_first_occurrence():
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20260107\r\nSUMMARY:First\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART:20260107\r\nSUMMARY:Second\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert result["01-07"] == "First"


def test_parse_ics_multiline_summary():
    # RFC 5545: long lines are folded with CRLF + space
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "DTSTART:20260301\r\n"
        "SUMMARY:Feast of Saint\r\n Thomas the Apostle\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    result = parse_ics(ics)
    assert "03-01" in result


def test_julian_civil_to_malankara_christmas():
    # Julian Dec 25 → Syriac ICS shows Jan 7 (Gregorian civil) → Malankara Dec 25
    assert julian_civil_to_malankara("01-07") == "12-25"


def test_julian_civil_to_malankara_new_year():
    # Julian Jan 1 → Syriac ICS shows Jan 14 → Malankara Jan 1
    assert julian_civil_to_malankara("01-14") == "01-01"


def test_julian_civil_to_malankara_offset():
    # Verify consistent 13-day offset across months
    assert julian_civil_to_malankara("03-14") == "03-01"
    assert julian_civil_to_malankara("04-14") == "04-01"
