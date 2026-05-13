from __future__ import annotations

import json
import urllib.request as _urllib_request
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .calendar_logic import (
    canonical_tradition_key,
    convert_to_tradition_month_day,
    effective_calendar,
    julian_pascha_as_gregorian,
)
from .calendar_logic import movable_feasts as _movable_feasts, moon_phase as _moon_phase
from .config import TRADITIONS
from .models import CalendarSystem, Contact, MovableFeastsResponse, MoonPhaseResponse, NameDayResponse, SaintsResponse
from .services.name_days import find_name_days
from .services.saints import get_saints_for_date
from .services.ical import generate_ical_feed


class NameDayRequest(BaseModel):
    date: date
    traditions: Optional[List[str]] = None
    contacts: List[Contact]


app = FastAPI(
    title="orthodox-calendar",
    description="Orthodox and Oriental Orthodox saints of the day with calendar/contacts hooks.",
    version="0.2.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/saints", response_model=List[SaintsResponse])
def saints(
    day: date = Query(default_factory=date.today),
    traditions: Optional[List[str]] = Query(default=None),
) -> List[SaintsResponse]:
    requested = traditions or list(TRADITIONS.keys())

    try:
        # Validate traditions early
        canonicalized = [canonical_tradition_key(t) for t in requested]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return get_saints_for_date(day, canonicalized)


@app.post("/api/v1/name-days", response_model=NameDayResponse)
def name_days(payload: NameDayRequest) -> NameDayResponse:
    requested = payload.traditions or list(TRADITIONS.keys())
    try:
        canonicalized = [canonical_tradition_key(t) for t in requested]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return find_name_days(payload.date, canonicalized, payload.contacts)


@app.get("/api/v1/calendar")
def month_calendar(
    year: int = Query(..., ge=1, le=9999),
    month: int = Query(..., ge=1, le=12),
    tradition: str = Query(default="serbian"),
) -> Dict[str, Any]:
    import calendar as _cal

    try:
        canonical = canonical_tradition_key(tradition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    days_in_month = _cal.monthrange(year, month)[1]
    result: Dict[str, Any] = {}

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        entries = get_saints_for_date(d, [canonical])
        if not entries or not entries[0].saints:
            continue
        saints_list = entries[0].saints
        feast_types = [s.feast_type for s in saints_list if s.feast_type]
        top = saints_list[0]
        result[d.isoformat()] = {
            "feast_types": feast_types,
            "main_feast": top.title or top.name,
            "calendar_date": entries[0].calendar_date,
        }

    return result


@app.get("/api/v1/readings")
def readings(
    day: date = Query(default_factory=date.today),
    tradition: str = Query(default="greek"),
) -> Dict[str, Any]:
    try:
        canonical = canonical_tradition_key(tradition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    trad = TRADITIONS[canonical]
    calendar = effective_calendar(day, trad)
    if calendar == CalendarSystem.JULIAN:
        cal = "julian"
        _, calendar_date = convert_to_tradition_month_day(day, trad)
        api_year, api_month, api_day = (int(part) for part in calendar_date.split("-"))
    else:
        cal = "gregorian"
        api_year, api_month, api_day = day.year, day.month, day.day
    url = f"https://orthocal.info/api/{cal}/{api_year}/{api_month}/{api_day}/"
    try:
        with _urllib_request.urlopen(url, timeout=8) as resp:  # noqa: S310
            return json.loads(resp.read())
    except Exception:
        return {}


@app.get("/api/v1/saints.ics")
def saints_ical(
    tradition: str,
    start: date = Query(default_factory=date.today),
    days: int = Query(default=365, ge=1, le=730),
):
    try:
        canonical_tradition_key(tradition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ical = generate_ical_feed(tradition, start, days)
    return Response(content=ical, media_type="text/calendar")


@app.get("/api/v1/movable-feasts", response_model=MovableFeastsResponse)
def get_movable_feasts(
    year: int = Query(..., ge=1, le=9999),
) -> MovableFeastsResponse:
    """Return all Eastern Orthodox movable feasts for the given year (Gregorian dates)."""
    pascha = julian_pascha_as_gregorian(year)
    feasts = _movable_feasts(year, pascha=pascha)
    return MovableFeastsResponse(year=year, pascha_gregorian=pascha.isoformat(), feasts=feasts)


@app.get("/api/v1/moon-phase", response_model=MoonPhaseResponse)
def get_moon_phase(
    day: date = Query(default_factory=date.today),
) -> MoonPhaseResponse:
    """Return lunar phase info for a given date."""
    info = _moon_phase(day)
    return MoonPhaseResponse(date=day, **info)
