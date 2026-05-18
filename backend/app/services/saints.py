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
    r"(https://www\.oca\.org/saints/lives/)\d{4}/(\d{2}/\d{2})/(.*)"
)


def _build_movable_meta() -> dict[int, tuple[str | None, str | None]]:
    """Pre-index Pascha-relative delta → (url_id_slug, notes) from OCA scraped data.

    Detects the dataset's scrape year automatically by finding the Pascha entry
    and matching its month_day against Julian Pascha dates for years 2020–2040.
    This avoids hardcoding a year that would break if the dataset is re-scraped.
    Notes are liturgically timeless and preserved as-is.  URL date portions are
    stripped (only the stable id-slug tail is kept) and reconstructed at serve time.
    """
    from datetime import date as _d

    # Locate the Pascha entry to determine the scrape year
    pascha_month_day: str | None = None
    for entry in _INDEX.get("oca", []):
        for s in entry.saints:
            tl = (s.title or "").lower()
            if ("pascha" in tl) and is_movable_feast_title(s.title or ""):
                pascha_month_day = entry.month_day
                break
        if pascha_month_day:
            break

    if not pascha_month_day:
        return {}

    mm, dd = int(pascha_month_day.split("-")[0]), int(pascha_month_day.split("-")[1])
    scrape_pascha: _d | None = None
    for year in range(2020, 2041):
        candidate = julian_pascha_as_gregorian(year)
        if candidate.month == mm and candidate.day == dd:
            scrape_pascha = candidate
            break

    if not scrape_pascha:
        return {}

    meta: dict[int, tuple[str | None, str | None]] = {}
    for entry in _INDEX.get("oca", []):
        em, ed = entry.month_day.split("-")
        try:
            key_date = _d(scrape_pascha.year, int(em), int(ed))
        except ValueError:
            continue
        delta = (key_date - scrape_pascha).days
        for s in entry.saints:
            if is_movable_feast_title(s.title or ""):
                url = s.hagiography_url
                id_slug: str | None = None
                if url:
                    m = _OCA_URL_DATE_RE.match(url)
                    id_slug = m.group(3) if m else None
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


def _fix_oca_url_year(url: str | None, calendar_date: str | None) -> str | None:
    """Replace the year in an OCA URL with the tradition's calendar year.

    OCA organises saints pages by Julian calendar date.  The dataset was scraped
    in 2024 so every URL contains the literal year 2024.  This function swaps
    that year for the year derived from *calendar_date* (the tradition's own
    calendar representation of the requested Gregorian date), which is:
      - the Julian year for Julian traditions (e.g. Serbian Christmas on
        Gregorian Jan 7 2026 → calendar_date "2025-12-25" → year 2025)
      - the Gregorian/Revised-Julian year for all other traditions
    Non-OCA URLs (no regex match) are returned unchanged.
    """
    if not url or not calendar_date:
        return url
    m = _OCA_URL_DATE_RE.match(url)
    if not m:
        return url
    calendar_year = calendar_date.split("-")[0]
    return f"{m.group(1)}{calendar_year}/{m.group(2)}/{m.group(3)}"


def _resolve_hagiography_url(saint: Saint, calendar_date: str | None = None) -> str | None:
    """Return the hagiography URL for the configured HAGIOGRAPHY_SOURCE.

    Always fixes the year in OCA URLs to match the tradition's calendar date
    (Julian year for Julian traditions, Gregorian year for all others).
    "goarch" → uses saint.goarch_url when set, then falls back to year-fixed OCA URL.
    """
    if HAGIOGRAPHY_SOURCE == "goarch":
        return saint.goarch_url or _fix_oca_url_year(saint.hagiography_url, calendar_date)
    return _fix_oca_url_year(saint.hagiography_url, calendar_date)


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
    if overlay.goarch_url and not base.goarch_url:
        base.goarch_url = overlay.goarch_url
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
        resolved_url = _resolve_hagiography_url(s, calendar_date)
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
        # Guard: only the OCA base dataset has 2024-scraped movable feast entries;
        # non-OCA Julian traditions (syriac, oriental) must not be affected.
        if cal in (CalendarSystem.JULIAN, CalendarSystem.REVISED) and base_key == "oca":
            base_entries = [
                e.model_copy(
                    update={"saints": [s for s in e.saints if not is_movable_feast_title(s.title or "")]}
                )
                for e in base_entries
            ]
            base_entries = [e for e in base_entries if e.saints]

            pascha = julian_pascha_as_gregorian(day.year)
            feast = movable_feast_for_date(day, pascha)
            if feast:
                feast_key, feast_title, feast_type = feast
                id_slug, notes = _MOVABLE_META.get((day - pascha).days, (None, None))
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

        if cal in (CalendarSystem.JULIAN, CalendarSystem.REVISED) and base_key == "oca":
            base_day = [
                e.model_copy(
                    update={"saints": [s for s in e.saints if not is_movable_feast_title(s.title or "")]}
                )
                for e in base_day
            ]
            base_day = [e for e in base_day if e.saints]
            feast = movable_feast_for_date(d, pascha_of_year)
            if feast:
                feast_key, feast_title, feast_type = feast
                id_slug, notes = _MOVABLE_META.get((d - pascha_of_year).days, (None, None))
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
