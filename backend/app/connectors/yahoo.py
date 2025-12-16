from __future__ import annotations

from typing import List

from .base import CalendarConnector, ContactConnector
from ..models import Contact, NameDayMatch


class YahooConnector(ContactConnector, CalendarConnector):
    source = "yahoo"

    def __init__(self, token_path: str | None = None):
        self.token_path = token_path

    def list_contacts(self) -> List[Contact]:
        # Placeholder: Yahoo address book API integration
        return []

    def schedule_name_day(self, match: NameDayMatch) -> None:
        # Placeholder: Yahoo Calendar integration
        return

