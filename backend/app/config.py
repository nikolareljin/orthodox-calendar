from __future__ import annotations

from typing import Dict

from .models import CalendarSystem, Tradition

# Canonical tradition metadata. These can be adjusted per deployment if a parish
# follows a different reckoning.
#
# data_key: saints lookup key. All Byzantine churches share the same sanctoral calendar.
# The base dataset is keyed as "oca" (Orthodox Church of America Julian Synaxarion) —
# a neutral, tradition-agnostic source for the full Byzantine sanctoral year.
#
# The Revised Julian calendar keeps the same NUMERICAL month/day for fixed feasts as
# the Old Julian (e.g., Christmas = "12-25" in both systems), so all Byzantine traditions
# can share the "oca" dataset regardless of calendar system. The civil date differs
# (Julian Dec 25 = Gregorian Jan 7; Revised Dec 25 = Gregorian Dec 25), but the
# month_day lookup key is identical — this is intentional and correct.
#
# Tradition-specific saints (local canonizations, regional martyrs) are stored in
# data/traditions/<tradition>.json and merged automatically on top of the base dataset.
TRADITIONS: Dict[str, Tradition] = {
    "greek": Tradition(
        name="Greek Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["greece", "hellenic", "ecumenical"],
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
        data_key="oca",
    ),
    "romanian": Tradition(
        name="Romanian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["patriarchate-of-romania"],
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
        data_key="oca",
    ),
    "alexandria": Tradition(
        name="Patriarchate of Alexandria",
        calendar=CalendarSystem.REVISED,
        aliases=["alexandrian"],
        data_key="oca",
    ),
    "ethiopian": Tradition(
        name="Ethiopian Orthodox Tewahedo",
        calendar=CalendarSystem.JULIAN,
        aliases=["tewahedo"],
    ),
    "oriental": Tradition(
        name="Oriental Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["coptic", "syriac", "malankara"],
    ),
    # Armenian Apostolic is Oriental (non-Chalcedonian), not Eastern Orthodox,
    # but included for reference alongside the Orthodox churches.
    "armenian": Tradition(
        name="Armenian Apostolic",
        calendar=CalendarSystem.JULIAN,
        aliases=["aac", "armenian-orthodox", "apostolic-armenian"],
    ),
}

