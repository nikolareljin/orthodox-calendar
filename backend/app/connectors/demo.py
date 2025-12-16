from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .base import CalendarConnector, ContactConnector
from ..models import Contact, NameDayMatch

DEMO_CONTACTS_ENV = "ORTHODOX_CALENDAR_DEMO_CONTACTS"


class DemoConnector(ContactConnector, CalendarConnector):
    """
    Minimal connector that reads contacts from a local JSON file for offline testing.
    Each entry should look like: {"full_name": "John Example", "source": "demo"}.
    """

    source = "demo"

    def __init__(self, path: str | None = None):
        env_path = os.getenv(DEMO_CONTACTS_ENV)
        self.path = Path(path or env_path or "demo_contacts.json")

    def list_contacts(self) -> List[Contact]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return [Contact(**entry) for entry in raw]

    def schedule_name_day(self, match: NameDayMatch) -> None:
        # Demo connector only logs locally; extend to write ICS or send notifications if desired.
        return

