from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CalendarSystem(str, Enum):
    GREGORIAN = "gregorian"
    REVISED = "revised"  # Milankovich / New Calendar
    JULIAN = "julian"


class Tradition(BaseModel):
    name: str
    calendar: CalendarSystem
    aliases: List[str] = Field(default_factory=list)
    # Gregorian date when a Revised Julian (Milankovich/New Calendar) tradition adopted it.
    reform_date: Optional[date] = None
    # When set, saints lookup uses this tradition's data instead of the tradition's own key.
    # Lets Jerusalem/Russian/Georgian share the Byzantine Julian sanctoral data without duplication.
    data_key: Optional[str] = None


class Saint(BaseModel):
    name: str
    name_hy: Optional[str] = None          # Armenian script name (Հայ)
    title: Optional[str] = None
    feast_type: Optional[str] = None
    hagiography_url: Optional[str] = None
    icon_url: Optional[str] = None
    notes: Optional[str] = None
    canonized_by: Optional[str] = None      # e.g. "Serbian Orthodox Church", "Ecumenical Patriarchate"
    canonization_scope: Optional[str] = None  # "universal" | "pan-orthodox" | "local" | "oriental"
    year_canonized: Optional[int] = None    # e.g. 2010


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


class MovableFeastsResponse(BaseModel):
    year: int
    pascha_gregorian: str  # ISO date
    feasts: Dict[str, str]  # feast_key -> ISO date (Gregorian)


class MoonPhaseResponse(BaseModel):
    date: date
    phase: float          # 0.0=new moon, 0.5=full moon, 1.0=back to new
    phase_name: str       # "New Moon", "Waxing Crescent", etc.
    emoji: str            # moon emoji
    illumination: float   # 0.0 to 1.0 approximate
