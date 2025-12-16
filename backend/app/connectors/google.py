from __future__ import annotations

from typing import List

from .base import CalendarConnector, ContactConnector
from ..models import Contact, NameDayMatch


class GoogleConnector(ContactConnector, CalendarConnector):
    source = "google"

    def __init__(self, credentials_path: str | None = None):
        self.credentials_path = credentials_path

    def list_contacts(self) -> List[Contact]:
        # Placeholder: wire Google People API here
        return []

    def schedule_name_day(self, match: NameDayMatch) -> None:
        # Placeholder: use Google Calendar API to create an all-day reminder
        return

