from __future__ import annotations

import calendar as _cal
import re as _re
from datetime import date
from typing import Any, Dict, List, Optional

from ..calendar_logic import (
    canonical_tradition_key,
    convert_to_tradition_month_day,
    effective_calendar,
    is_movable_feast_title,
    julian_pascha_as_gregorian,
    movable_feast_for_date,
    resolve_tradition,
)
from ..config import HAGIOGRAPHY_SOURCE
from ..data_loader import build_index
from ..models import CalendarEntry, CalendarSystem, Saint, SaintsResponse

_INDEX = build_index()


_OCA_URL_DATE_RE = _re.compile(
    r"(https://www\.oca\.org/saints/lives/)\d{4}/\d{2}/\d{2}/(.*)"
)


def _build_movable_meta() -> dict[int, tuple[str | None, str | None]]:
    """Pre-index Pascha-relative delta → (url_id_slug, notes) from 2024 OCA data.

    The OCA dataset was scraped in 2024, so each movable feast entry lives at
    its 2024 Gregorian key.  Notes are liturgically timeless and are preserved
    as-is.  URLs have the date portion stripped (only the stable id-slug tail
    is kept) so they can be reconstructed with the correct date at injection.
    """
    from datetime import date as _d
    pascha_2024 = _d(2024, 5, 5)
    meta: dict[int, tuple[str | None, str | None]] = {}
    for entry in _INDEX.get("oca", []):
        mm, dd = entry.month_day.split("-")
        try:
            key_date = _d(2024, int(mm), int(dd))
        except ValueError:
            continue
        delta = (key_date - pascha_2024).days
        for s in entry.saints:
            if is_movable_feast_title(s.title or ""):
                url = s.hagiography_url
                id_slug: str | None = None
                if url:
                    m = _OCA_URL_DATE_RE.match(url)
                    id_slug = m.group(2) if m else None
                meta[delta] = (id_slug, s.notes)
                break
    return meta


_MOVABLE_META: dict[int, tuple[str | None, str | None]] = _build_movable_meta()


def _oca_feast_url(id_slug: str | None, feast_date: date) -> str | None:
    """Reconstruct a year-correct OCA URL for a dynamically computed movable feast."""
    if not id_slug:
        return None
    return (
        f"https://www.oca.org/saints/lives/"
        f"{feast_date.year}/{feast_date.month:02d}/{feast_date.day:02d}/{id_slug}"
    )


def _resolve_hagiography_url(saint: Saint) -> str | None:
    """Return the hagiography URL for the configured HAGIOGRAPHY_SOURCE.

    "oca"   → saint.hagiography_url (OCA; for movable feasts this is already
               year-correct via _oca_feast_url; for fixed feasts the 2024 date
               in the URL is cosmetically stale but OCA serves by ID slug).
    "goarch" → saint.goarch_url when set; falls back to OCA URL so saints
               without a GOARCH content ID are still reachable.
               Enrich the dataset with goarch_url fields to get full GOARCH coverage.
    """
    if HAGIOGRAPHY_SOURCE == "goarch":
        return saint.goarch_url or saint.hagiography_url
    return saint.hagiography_url


# Common honorific prefixes that vary across sources for the same saint
# (e.g. base has "Seraphim of Sarov", overlay has "Saint Seraphim of Sarov").
_HONORIFIC_RE = _re.compile(
    r"^(?:(?:saint|st\.|st|venerable|blessed|holy|new martyr|hieromartyr|martyr)\s+)+",
    _re.IGNORECASE,
)
_EVENT_PREFIX_RE = _re.compile(
    r"^(?:(?:translation|uncovering|discovery|opening) of (?:the )?relics of "
    r"|(?:repose|translation|uncovering|discovery|opening) of (?:the )?)+",
    _re.IGNORECASE,
)
_DROP_TOKENS = {
    "saint",
    "st",
    "venerable",
    "blessed",
    "holy",
    "hieromartyr",
    "martyr",
    "new",
    "righteous",
    "wonderworker",
    "great",
    "of",
    "the",
}


def _normalize_saint_text(value: str) -> str:
    value = _EVENT_PREFIX_RE.sub("", value.lower().strip())
    value = _HONORIFIC_RE.sub("", value)
    value = _re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in _DROP_TOKENS]
    return " ".join(tokens)


def _saint_keys(saint: Saint) -> List[str]:
    """Stable dedup aliases from normalized title, name, and hagiography slug.

    Different sources phrase the same commemoration differently (e.g. "Repose
    of Venerable Seraphim" vs "Seraphim of Sarov"). Multiple aliases let
    overlays merge when any stable representation matches.
    """
    raw_values = [saint.title, saint.name]
    if saint.hagiography_url:
        raw_values.append(saint.hagiography_url.rsplit("/", 1)[-1])

    keys: List[str] = []
    for raw in raw_values:
        if not raw:
            continue
        key = _normalize_saint_text(raw)
        if key and key not in keys:
            keys.append(key)
    return keys or [saint.name.lower().strip()]


def _apply_overlay(base: Saint, overlay: Saint) -> None:
    """Merge overlay fields into base saint in-place.

    Overlay entries carry tradition-specific canonization data and richer
    hagiography fields that the shared base dataset may lack.
    """
    if overlay.title and not base.title:
        base.title = overlay.title
    if overlay.feast_type and not base.feast_type:
        base.feast_type = overlay.feast_type
    if overlay.hagiography_url and not base.hagiography_url:
        base.hagiography_url = overlay.hagiography_url
    if overlay.icon_url and not base.icon_url:
        base.icon_url = overlay.icon_url
    if overlay.notes and not base.notes:
        base.notes = overlay.notes
    if overlay.canonized_by and not base.canonized_by:
        base.canonized_by = overlay.canonized_by
    if overlay.canonization_scope and not base.canonization_scope:
        base.canonization_scope = overlay.canonization_scope
    if overlay.year_canonized and not base.year_canonized:
        base.year_canonized = overlay.year_canonized


def _build_month_day_index(entries: List[CalendarEntry]) -> Dict[str, List[CalendarEntry]]:
    by_md: Dict[str, List[CalendarEntry]] = {}
    for e in entries:
        by_md.setdefault(e.month_day, []).append(e)
    return by_md


def _merge_entries(
    day: date,
    tradition_name: str,
    calendar_date: str,
    day_entries: List[CalendarEntry],
) -> SaintsResponse:
    from ..calendar_logic import resolve_tradition as _resolve
    tradition = _resolve(tradition_name)
    merged: Dict[str, Saint] = {}
    key_index: Dict[str, str] = {}
    merged_notes: Optional[str] = None
    for entry in day_entries:
        for saint in entry.saints:
            keys = _saint_keys(saint)
            primary_key = next((key_index[key] for key in keys if key in key_index), None)
            if primary_key:
                _apply_overlay(merged[primary_key], saint)
                for key in keys:
                    key_index.setdefault(key, primary_key)
            else:
                primary_key = keys[0]
                merged[primary_key] = saint.model_copy()
                for key in keys:
                    key_index[key] = primary_key
        if entry.notes and not merged_notes:
            merged_notes = entry.notes
    saints_out = []
    for s in merged.values():
        resolved_url = _resolve_hagiography_url(s)
        if resolved_url != s.hagiography_url:
            s = s.model_copy(update={"hagiography_url": resolved_url})
        saints_out.append(s)
    return SaintsResponse(
        date=day,
        tradition=tradition.name,
        calendar_date=calendar_date,
        saints=saints_out,
        calendar_system=effective_calendar(day, tradition),
        notes=merged_notes,
    )


def get_saints_for_date(day: date, traditions: List[str]) -> List[SaintsResponse]:
    responses: List[SaintsResponse] = []
    for tradition_name in traditions:
        tradition = resolve_tradition(tradition_name)
        canonical = canonical_tradition_key(tradition_name)
        month_day, calendar_date = convert_to_tradition_month_day(day, tradition)
        cal = effective_calendar(day, tradition)

        base_key = tradition.data_key or canonical
        base_entries = [e for e in _INDEX.get(base_key, []) if e.month_day == month_day]
        # Tradition-specific overlays are intentional and must never be filtered.
        overlay_entries = (
            [e for e in _INDEX.get(canonical, []) if e.month_day == month_day]
            if tradition.data_key
            else []
        )

        # Julian and Revised-Julian traditions share the Byzantine computus.
        # The OCA base dataset stores movable feasts at their 2024 Gregorian
        # dates — wrong for every other year.  Strip those entries from the
        # base data only, then inject the correctly computed feast for the
        # requested year.  Tradition overlays are left untouched.
        if cal in (CalendarSystem.JULIAN, CalendarSystem.REVISED):
            base_entries = [
                e.model_copy(
                    update={"saints": [s for s in e.saints if not is_movable_feast_title(s.title or "")]}
                )
                for e in base_entries
            ]
            base_entries = [e for e in base_entries if e.saints]

            feast = movable_feast_for_date(day)
            if feast:
                feast_key, feast_title, feast_type = feast
                delta = (day - julian_pascha_as_gregorian(day.year)).days
                id_slug, notes = _MOVABLE_META.get(delta, (None, None))
                movable_entry = CalendarEntry(
                    month_day=month_day,
                    tradition=base_key,
                    calendar=cal,
                    saints=[Saint(
                        name=feast_key, title=feast_title, feast_type=feast_type,
                        hagiography_url=_oca_feast_url(id_slug, day),
                        notes=notes,
                    )],
                )
                base_entries = [movable_entry] + base_entries

        day_entries = base_entries + overlay_entries

        if not day_entries:
            continue

        responses.append(_merge_entries(day, tradition_name, calendar_date, day_entries))
    return responses


def get_saints_for_month(year: int, month: int, tradition_name: str) -> Dict[str, Any]:
    """Return {date_iso: {feast_types, main_feast, calendar_date}} for days with saints.

    Pre-groups the index by month_day once (O(N)) instead of scanning per day
    (O(N * days_in_month)).
    """
    tradition = resolve_tradition(tradition_name)
    canonical = canonical_tradition_key(tradition_name)
    base_key = tradition.data_key or canonical

    base_by_md = _build_month_day_index(_INDEX.get(base_key, []))
    overlay_by_md = _build_month_day_index(_INDEX.get(canonical, [])) if tradition.data_key else {}
    pascha_of_year = julian_pascha_as_gregorian(year)

    result: Dict[str, Any] = {}
    for day_num in range(1, _cal.monthrange(year, month)[1] + 1):
        d = date(year, month, day_num)
        month_day, calendar_date = convert_to_tradition_month_day(d, tradition)
        cal = effective_calendar(d, tradition)

        base_day = list(base_by_md.get(month_day, []))
        overlay_day = list(overlay_by_md.get(month_day, [])) if overlay_by_md else []

        if cal in (CalendarSystem.JULIAN, CalendarSystem.REVISED):
            base_day = [
                e.model_copy(
                    update={"saints": [s for s in e.saints if not is_movable_feast_title(s.title or "")]}
                )
                for e in base_day
            ]
            base_day = [e for e in base_day if e.saints]
            feast = movable_feast_for_date(d)
            if feast:
                feast_key, feast_title, feast_type = feast
                delta = (d - pascha_of_year).days
                id_slug, notes = _MOVABLE_META.get(delta, (None, None))
                base_day = [
                    CalendarEntry(
                        month_day=month_day,
                        tradition=base_key,
                        calendar=cal,
                        saints=[Saint(
                            name=feast_key, title=feast_title, feast_type=feast_type,
                            hagiography_url=_oca_feast_url(id_slug, d),
                            notes=notes,
                        )],
                    )
                ] + base_day

        day_entries = base_day + overlay_day
        if not day_entries:
            continue

        resp = _merge_entries(d, tradition_name, calendar_date, day_entries)
        if not resp.saints:
            continue

        feast_types = [s.feast_type for s in resp.saints if s.feast_type]
        top = resp.saints[0]
        result[d.isoformat()] = {
            "feast_types": feast_types,
            "main_feast": top.title or top.name,
            "calendar_date": calendar_date,
        }
    return result
