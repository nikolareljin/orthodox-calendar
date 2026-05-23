from __future__ import annotations

import json
import os
import urllib.error as _urllib_error
import urllib.request as _urllib_request
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .calendar_logic import (
    canonical_tradition_key,
    effective_calendar,
    julian_pascha_as_gregorian,
)
from .calendar_logic import movable_feasts as _movable_feasts, moon_phase as _moon_phase
from .config import HAGIOGRAPHY_SOURCE, TRADITIONS
from .models import CalendarSystem, Contact, HagiographyResponse, MovableFeastsResponse, MoonPhaseResponse, NameDayResponse, SaintsResponse
from .services.name_days import find_name_days
from .services.saints import get_hagiography, get_saints_for_date, get_saints_for_month
from .services.ical import generate_ical_feed


DEFAULT_CORS_ORIGINS = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://nikolareljin.github.io",
]


def _cors_origins() -> list[str]:
    raw = os.getenv("ORTHODOX_CALENDAR_CORS_ORIGINS", "")
    if not raw.strip():
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class NameDayRequest(BaseModel):
    date: date
    traditions: Optional[List[str]] = None
    contacts: List[Contact]


app = FastAPI(
    title="orthodox-calendar",
    description="Orthodox and Oriental Orthodox saints of the day with calendar/contacts hooks.",
    version="0.6.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/config")
def api_config() -> dict:
    """Expose active runtime configuration for frontend/diagnostic use."""
    return {"hagiography_source": HAGIOGRAPHY_SOURCE}


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


@app.get("/api/v1/hagiography", response_model=HagiographyResponse)
def hagiography(
    saint: str = Query(..., min_length=1, description="Saint name (prefix/substring token match after normalization)"),
    date: Optional[str] = Query(
        default=None,
        description=(
            "Byzantine fixed-feast MM-DD key (Julian/Revised-Julian calendar). "
            "When provided, only saints commemorated on this date are considered; "
            "non-Byzantine calendars (Coptic, Ethiopian) use different MM-DD spaces "
            "and are not reliably filtered by this parameter."
        ),
        pattern=r"^\d{2}-\d{2}$",
    ),
) -> HagiographyResponse:
    """Return hagiography data for a named saint.

    Searches across all tradition datasets. If date (MM-DD) is given, only
    saints commemorated on that date are considered; no fallback to a full
    scan is performed. Whitespace-only saint names are rejected with 422.
    Source field indicates where the data came from: goarch, oca, notes, or not_found.
    """
    if not saint.strip():
        raise HTTPException(status_code=422, detail="saint must not be blank")
    return get_hagiography(saint, date)


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
    try:
        canonical = canonical_tradition_key(tradition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return get_saints_for_month(year, month, canonical)


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
    # orthocal.info always takes civil (Gregorian) dates — do NOT convert to
    # Julian calendar date before calling. The "julian" path selects the Old-
    # Calendar liturgical cycle (fixed feasts + movable feasts relative to Julian
    # Pascha); the "gregorian" path selects the New/Revised-Julian cycle.
    #
    # Empirically verified (civil 2026-05-19 = Julian 2026-05-06):
    #   julian/2026/5/6  → weekday=3 (Wed), "4th Sunday of Pascha"  ← WRONG
    #   julian/2026/5/19 → weekday=2 (Tue), "6th Sunday of Pascha"  ← correct
    # Passing the Julian calendar date is the bug this line intentionally avoids.
    cal = "julian" if calendar == CalendarSystem.JULIAN else "gregorian"
    api_year, api_month, api_day = day.year, day.month, day.day
    url = f"https://orthocal.info/api/{cal}/{api_year}/{api_month}/{api_day}/"
    try:
        with _urllib_request.urlopen(url, timeout=8) as resp:  # noqa: S310
            return json.loads(resp.read())
    except _urllib_error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Readings upstream returned HTTP {exc.code}") from exc
    except (_urllib_error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="Readings upstream is unavailable") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Readings upstream returned invalid JSON") from exc


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
