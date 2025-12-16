from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CalendarSystem(str, Enum):
    GREGORIAN = "gregorian"
    REVISED = "revised"  # Milankovich / New Calendar
    JULIAN = "julian"


class Tradition(BaseModel):
    name: str
    calendar: CalendarSystem
    aliases: List[str] = Field(default_factory=list)


class Saint(BaseModel):
    name: str
    title: Optional[str] = None
    feast_type: Optional[str] = None
    hagiography_url: Optional[str] = None
    icon_url: Optional[str] = None
    notes: Optional[str] = None


class CalendarEntry(BaseModel):
    month_day: str  # MM-DD on the tradition's calendar
    tradition: str
    calendar: CalendarSystem
    saints: List[Saint]
    notes: Optional[str] = None


class SaintsResponse(BaseModel):
    date: date
    tradition: str
    calendar_date: str
    saints: List[Saint]
    calendar_system: CalendarSystem
    notes: Optional[str] = None


class Contact(BaseModel):
    full_name: str
    source: Optional[str] = None  # google, outlook, yahoo, facebook, manual
    id: Optional[str] = None


class NameDayMatch(BaseModel):
    contact: Contact
    saint: Saint
    tradition: str
    date: date
    calendar_system: CalendarSystem


class NameDayResponse(BaseModel):
    matches: List[NameDayMatch]
    checked_date: date

