from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel

from .calendar_logic import canonical_tradition_key
from .config import TRADITIONS
from .models import Contact, NameDayResponse, SaintsResponse
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
    version="0.1.0",
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
