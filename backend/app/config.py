from __future__ import annotations

from datetime import date
from typing import Dict

from .models import CalendarSystem, Tradition

# Canonical tradition metadata. These can be adjusted per deployment if a parish
# follows a different reckoning.
#
# data_key: saints lookup key. All Byzantine churches share the same sanctoral calendar.
# The base dataset is keyed as "oca" (Orthodox Church of America Julian Synaxarion) —
# a neutral, tradition-agnostic source for the full Byzantine sanctoral year.
#
# The Revised Julian (Milankovich/New Calendar) uses the same fixed-feast
# month/day keys as the Old Julian calendar (e.g., Christmas = "12-25"), so all
# Byzantine traditions can share the "oca" dataset. Civil-date conversion is
# still calendar-specific: Revised and Gregorian align through February 2800,
# then diverge under Milankovich's 900-year leap rule.
#
# reform_date: first Gregorian date on which this church follows the Revised Julian
# (Milankovich/New Calendar) for fixed feasts. Before that date, revised-calendar
# traditions are treated as Julian for historical lookups.
#
# Tradition-specific saints (local canonizations, regional martyrs) are stored in
# data/traditions/<tradition>_saints.json and merged automatically on top of the base dataset.
TRADITIONS: Dict[str, Tradition] = {
    "greek": Tradition(
        name="Ecumenical Patriarchate of Constantinople",
        calendar=CalendarSystem.REVISED,
        aliases=["greece", "hellenic", "ecumenical", "constantinople", "greek orthodox"],
        reform_date=date(1924, 3, 23),
        data_key="oca",
    ),
    "russian": Tradition(
        name="Russian Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["roc", "moscow"],
        data_key="oca",  # base: shared Byzantine Julian dataset; overlay: russian_saints.json
    ),
    "serbian": Tradition(
        name="Serbian Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["spc", "serbia"],
        data_key="oca",
    ),
    "bulgarian": Tradition(
        name="Bulgarian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["bogk"],
        reform_date=date(1968, 12, 20),
        data_key="oca",
    ),
    "cyprus": Tradition(
        name="Church of Cyprus",
        calendar=CalendarSystem.REVISED,
        aliases=["cypriot", "cyprus-orthodox"],
        reform_date=date(1924, 3, 23),
        data_key="oca",
    ),
    "romanian": Tradition(
        name="Romanian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["patriarchate-of-romania"],
        reform_date=date(1924, 10, 14),
        data_key="oca",
    ),
    "jerusalem": Tradition(
        name="Patriarchate of Jerusalem",
        calendar=CalendarSystem.JULIAN,
        aliases=["jerusalem-patriarchate", "jerusalem-orthodox"],
        data_key="oca",
    ),
    "georgian": Tradition(
        name="Georgian Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["goc", "patriarchate-of-georgia"],
        data_key="oca",
    ),
    "antioch": Tradition(
        name="Antiochian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["antiochian"],
        reform_date=date(1928, 10, 14),
        data_key="oca",
    ),
    "alexandria": Tradition(
        name="Patriarchate of Alexandria",
        calendar=CalendarSystem.REVISED,
        aliases=["alexandrian"],
        reform_date=date(1928, 10, 14),
        data_key="oca",
    ),
    "ethiopian": Tradition(
        name="Ethiopian Orthodox Tewahedo",
        # Ethiopian Orthodox uses the Ethiopian (Ge'ez) calendar liturgically. Import scripts
        # convert Ge'ez days to civil (Gregorian) MM-DD for storage; ETHIOPIAN falls through
        # to the Gregorian lookup path so no date conversion is applied.
        calendar=CalendarSystem.ETHIOPIAN,
        aliases=["tewahedo"],
    ),
    "syriac": Tradition(
        name="Syriac Orthodox Church of Antioch",
        calendar=CalendarSystem.JULIAN,
        aliases=["jacobite", "syriac-orthodox", "suryoyo"],
        # Julian-keyed dataset built by import_syriac.py
    ),
    # "oriental" is a legacy key retained for API compatibility. It serves the small
    # oriental_saints.json dataset (6 entries). Syriac and Malankara each now have
    # dedicated datasets/config entries; Coptic moved to the "coptic" key below.
    "oriental": Tradition(
        name="Oriental Orthodox (shared)",
        calendar=CalendarSystem.JULIAN,
        aliases=["oriental orthodox", "oriental-orthodox"],
    ),
    # Coptic Orthodox uses the Coptic (Alexandrian) calendar liturgically. Data from coptic.io
    # is keyed by civil (Gregorian) MM-DD dates; COPTIC falls through to the Gregorian lookup
    # path so no date conversion is applied.
    "coptic": Tradition(
        name="Coptic Orthodox Church of Alexandria",
        calendar=CalendarSystem.COPTIC,
        aliases=["coptic-orthodox", "alexandria-coptic"],
    ),
    "malankara": Tradition(
        name="Malankara Orthodox Syrian Church",
        calendar=CalendarSystem.GREGORIAN,
        aliases=["mosc", "indian-orthodox", "thomas-christians"],
    ),
    "assyrian": Tradition(
        name="Assyrian Church of the East",
        calendar=CalendarSystem.GREGORIAN,
        aliases=["church-of-the-east", "coe", "nestorian"],
        # Gregorian-keyed dataset scraped from calendar.assyrianchurch.org
    ),
    # Armenian Apostolic is Oriental/Non-Chalcedonian, included alongside the Orthodox churches.
    # Gregorian-keyed: armenianchurch.org publishes feast dates in Gregorian (DD.MM.YYYY).
    "armenian": Tradition(
        name="Armenian Apostolic",
        calendar=CalendarSystem.GREGORIAN,
        aliases=["aac", "armenian-orthodox", "apostolic-armenian"],
    ),
}
