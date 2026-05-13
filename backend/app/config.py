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
        data_key="oca",
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
        calendar=CalendarSystem.JULIAN,
        aliases=["tewahedo"],
    ),
    "syriac": Tradition(
        name="Syriac Orthodox Church of Antioch",
        calendar=CalendarSystem.JULIAN,
        aliases=["jacobite", "syriac-orthodox", "suryoyo"],
        data_key="oriental",   # shares Oriental Orthodox sanctoral data until Syriac-specific set is built
    ),
    "oriental": Tradition(
        name="Coptic Orthodox Church of Alexandria",
        calendar=CalendarSystem.JULIAN,
        aliases=["coptic", "oriental orthodox", "oriental-orthodox"],
    ),
    "malankara": Tradition(
        name="Malankara Orthodox Syrian Church",
        calendar=CalendarSystem.JULIAN,
        aliases=["mosc", "indian-orthodox", "thomas-christians"],
        data_key="oriental",   # shares Oriental Orthodox sanctoral data until Malankara-specific set is built
    ),
    "assyrian": Tradition(
        name="Assyrian Church of the East",
        calendar=CalendarSystem.JULIAN,
        aliases=["church-of-the-east", "coe", "nestorian"],
        # No data_key: distinct sanctoral calendar — returns empty saints list until dedicated dataset is added
    ),
    # Armenian Apostolic is Oriental/Non-Chalcedonian, included alongside the Orthodox churches.
    "armenian": Tradition(
        name="Armenian Apostolic",
        calendar=CalendarSystem.JULIAN,
        aliases=["aac", "armenian-orthodox", "apostolic-armenian"],
    ),
}
