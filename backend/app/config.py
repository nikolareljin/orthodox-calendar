from __future__ import annotations

from typing import Dict

from .models import CalendarSystem, Tradition

# Canonical tradition metadata. These can be adjusted per deployment if a parish
# follows a different reckoning.
TRADITIONS: Dict[str, Tradition] = {
    "greek": Tradition(
        name="Greek Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["greece", "hellenic"],
    ),
    "russian": Tradition(
        name="Russian Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["roc", "moscow"],
    ),
    "serbian": Tradition(
        name="Serbian Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["spc", "serbia"],
    ),
    "bulgarian": Tradition(
        name="Bulgarian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["bogk"],
    ),
    "romanian": Tradition(
        name="Romanian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["patriarchate-of-romania"],
    ),
    "jerusalem": Tradition(
        name="Patriarchate of Jerusalem",
        calendar=CalendarSystem.JULIAN,
        aliases=["jerusalem-patriarchate", "jerusalem-orthodox"],
    ),
    "antioch": Tradition(
        name="Antiochian Orthodox",
        calendar=CalendarSystem.REVISED,
        aliases=["antiochian"],
    ),
    "alexandria": Tradition(
        name="Patriarchate of Alexandria",
        calendar=CalendarSystem.REVISED,
        aliases=["alexandrian"],
    ),
    "ethiopian": Tradition(
        name="Ethiopian Orthodox Tewahedo",
        calendar=CalendarSystem.JULIAN,
        aliases=["tewahedo"],
    ),
    "oriental": Tradition(
        name="Oriental Orthodox",
        calendar=CalendarSystem.JULIAN,
        aliases=["coptic", "armenian", "syriac", "malankara"],
    ),
}

