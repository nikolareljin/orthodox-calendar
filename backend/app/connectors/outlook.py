from __future__ import annotations

from typing import List

from .base import CalendarConnector, ContactConnector
from ..models import Contact, NameDayMatch


class OutlookConnector(ContactConnector, CalendarConnector):
    source = "outlook"

    def __init__(self, token_path: str | None = None):
        self.token_path = token_path

    def list_contacts(self) -> List[Contact]:
        # Placeholder: wire Microsoft Graph API here
        return []

    def schedule_name_day(self, match: NameDayMatch) -> None:
        # Placeholder: create an Outlook calendar event/notification
        return

