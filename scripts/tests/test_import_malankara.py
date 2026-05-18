import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from import_malankara import (
    parse_ics,
    julian_civil_to_malankara,
    clean_name,
    is_substantive,
    feast_type,
    normalize_key,
    make_saint,
    make_entry,
    merge_into,
)


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
    assert result["03-01"] == "Feast of Saint Thomas the Apostle"


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


def test_clean_name_strips_saint_prefix():
    assert clean_name("Saint Thomas the Apostle") == "Thomas the Apostle"
    assert clean_name("Saints Peter and Paul") == "Peter and Paul"
    assert clean_name("St. Mary the Virgin") == "Mary the Virgin"


def test_clean_name_strips_event_prefix():
    assert clean_name("Feast of the Nativity") == "Nativity"
    assert clean_name("Commemoration of the Holy Martyrs") == "Holy Martyrs"


def test_is_substantive_keeps_saints_and_feasts():
    assert is_substantive("Feast of Saint Thomas the Apostle")
    assert is_substantive("Commemoration of the Holy Martyrs")
    assert is_substantive("NATIVITY OF OUR LORD")
    assert is_substantive("Perunnal of Saint Mary")
    assert is_substantive("Thirunal of the Apostle")


def test_is_substantive_drops_noise():
    assert not is_substantive("Fast day")
    assert not is_substantive("Lenten weekday")
    assert not is_substantive("")
    assert not is_substantive("Sunday of the Great Lent")


def test_feast_type_detection():
    assert feast_type("Saint Thomas the Martyr") == "Martyr"
    assert feast_type("Hieromartyr Ignatius") == "Hieromartyr"
    assert feast_type("Venerable Ephrem the Syrian") == "Venerable"
    assert feast_type("Feast of the Nativity") == "Feast"
    assert feast_type("Perunnal of Our Lady") == "Feast"
    assert feast_type("Thirunal of the church") == "Feast"
    assert feast_type("Apostle Thomas") == "Apostle"
    assert feast_type("Prophet Elijah") == "Prophet"
    assert feast_type("Some unknown celebration") == "Saint"


def test_normalize_key_deduplicates_same_saint():
    assert normalize_key("Saint Thomas") == normalize_key("Thomas")
    assert normalize_key("St. Mary") == normalize_key("Mary")


def test_merge_into_adds_new_date():
    base = [make_entry("01-07", [make_saint("Nativity")])]
    new  = [make_entry("01-14", [make_saint("New Year")])]
    result = merge_into(base, new)
    assert len(result) == 2
    assert result[0]["month_day"] == "01-07"
    assert result[1]["month_day"] == "01-14"


def test_merge_into_deduplicates_same_saint():
    base = [make_entry("07-03", [make_saint("Thomas")])]
    dupe = [make_entry("07-03", [make_saint("Saint Thomas")])]
    result = merge_into(base, dupe)
    assert len(result[0]["saints"]) == 1


def test_merge_into_enriches_existing():
    base = [make_entry("07-03", [make_saint("Thomas")])]
    rich = [make_entry("07-03", [make_saint("Thomas", hagiography_url="https://en.wikipedia.org/wiki/Thomas")])]
    result = merge_into(base, rich)
    assert result[0]["saints"][0]["hagiography_url"] == "https://en.wikipedia.org/wiki/Thomas"


def test_merge_into_adds_new_saint_same_date():
    base = [make_entry("07-03", [make_saint("Thomas")])]
    new  = [make_entry("07-03", [make_saint("Mary Magdalene")])]
    result = merge_into(base, new)
    assert len(result[0]["saints"]) == 2


def test_make_saint_sets_required_fields():
    s = make_saint("Nativity of Our Lord")
    assert s["name"] == "Nativity of Our Lord"
    assert s["feast_type"] == "Feast"
    assert s["canonized_by"] == "Malankara Orthodox Syrian Church"
    assert s["canonization_scope"] == "oriental"


def test_make_saint_clean_name_applied():
    s = make_saint("Saint Thomas the Apostle")
    assert s["name"] == "Thomas the Apostle"    # clean_name stripped "Saint "
    assert s["title"] == "Saint Thomas the Apostle"  # title preserved raw


def test_make_entry_structure():
    e = make_entry("12-25", [make_saint("Nativity")])
    assert e["tradition"] == "malankara"
    assert e["calendar"] == "gregorian"
    assert e["month_day"] == "12-25"
