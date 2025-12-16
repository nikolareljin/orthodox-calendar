from __future__ import annotations

from typing import List

from .base import CalendarConnector, ContactConnector
from ..models import Contact, NameDayMatch


class FacebookConnector(ContactConnector, CalendarConnector):
    source = "facebook"

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self.app_id = app_id
        self.app_secret = app_secret

    def list_contacts(self) -> List[Contact]:
        # Placeholder: Facebook Graph API for friends list
        return []

    def schedule_name_day(self, match: NameDayMatch) -> None:
        # Placeholder: post/share a reminder or send a message
        return

