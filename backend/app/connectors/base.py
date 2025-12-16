from __future__ import annotations

from typing import List

from ..models import Contact, NameDayMatch


class ContactConnector:
    """Base connector for pulling contacts from an external source."""

    source: str = "unknown"

    def list_contacts(self) -> List[Contact]:
        raise NotImplementedError


class CalendarConnector:
    """Base connector for pushing name-day reminders to external calendars."""

    source: str = "unknown"

    def schedule_name_day(self, match: NameDayMatch) -> None:
        raise NotImplementedError

