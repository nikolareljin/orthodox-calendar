"""Regression tests for the GOARCH ICS importer.

Covers the two parsing defects found in review: a greedy DESCRIPTION match that
swallowed the rest of the VEVENT, and a title-prefix regex that was defined but
never applied.
"""

import import_goarch_ics as igi

# A VEVENT with DESCRIPTION *before* UID/DTEND, which is the ordering that
# exposed the greedy match. Folded continuation lines start with a space, per
# RFC 5545, and _parse_events unfolds them before matching.
_ICS = (
    "BEGIN:VCALENDAR\r\n"
    "BEGIN:VEVENT\r\n"
    "DTSTART;VALUE=DATE:20250101\r\n"
    "SUMMARY:Circumcision of Our Lord\r\n"
    "DESCRIPTION:Saints and Feasts: Circumcision of Our Lord; Basil the Great;\r\n"
    "  Righteous Theodosios of Triglia\\n\\nReadings: Col 2:8-12\r\n"
    "UID:goarch-20250101@example.invalid\r\n"
    "DTEND;VALUE=DATE:20250102\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_description_does_not_swallow_later_properties():
    (event,) = igi._parse_events(_ICS)
    joined = " ".join(event["saints"])
    assert "UID" not in joined
    assert "DTEND" not in joined
    assert "goarch-20250101" not in joined


def test_folded_description_still_yields_all_saints():
    (event,) = igi._parse_events(_ICS)
    assert "Basil the Great" in event["saints"]
    # The saint on the folded continuation line must survive unfolding.
    assert "Righteous Theodosios of Triglia" in event["saints"]


def test_saints_section_stops_at_readings():
    (event,) = igi._parse_events(_ICS)
    assert not any("Readings" in s for s in event["saints"])


def test_clean_name_strips_leading_honorific():
    assert igi._clean_name("Righteous Theodosios of Triglia") == "Theodosios of Triglia"
    assert igi._clean_name("Saint Basil the Great") == "Basil the Great"


def test_clean_name_strips_stacked_honorifics():
    assert igi._clean_name("Holy Martyrs Sergius and Bacchus") == "Sergius and Bacchus"


def test_clean_name_never_empties_an_all_honorific_name():
    # The pattern requires trailing whitespace, so the final token survives and
    # the commemoration is never dropped by dropping below the length guard.
    assert igi._clean_name("Holy Martyrs") == "Martyrs"
    assert igi._clean_name("Saint") == "Saint"


def test_clean_name_removes_parentheticals():
    assert igi._clean_name("Saint Nicholas (the Wonderworker)") == "Nicholas"


def test_clean_title_keeps_the_honorific():
    assert igi._clean_title("Righteous Theodosios of Triglia") == "Righteous Theodosios of Triglia"
    # Parentheticals and whitespace are still normalized.
    assert igi._clean_title("Saint  Nicholas (the Wonderworker)") == "Saint Nicholas"


def test_entries_carry_prefix_free_name_and_honorific_title():
    events = [{"month_day": "01-01", "summary": "", "saints": ["Righteous Mark the Deaf"]}]
    (entry,) = igi.events_to_entries(events)
    (saint,) = entry["saints"]
    assert saint["name"] == "Mark the Deaf"
    assert saint["title"] == "Righteous Mark the Deaf"
    # feast_type is derived from the raw name, so the honorific still classifies it.
    assert saint["feast_type"] == "Righteous"
