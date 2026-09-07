from __future__ import annotations

import calendar as _cal
import functools
import re as _re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

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
from ..models import CalendarEntry, CalendarSystem, HagiographyResponse, Saint, SaintsResponse

_INDEX = build_index()


_OCA_URL_DATE_RE = _re.compile(
    r"(https://www\.oca\.org/saints/lives/)(\d{4})/(\d{2}/\d{2})/(.*)"
)
_OCA_ZERO_YEAR_RE = _re.compile(
    r"(https://www\.oca\.org/saints/lives/)0000/(\d{2}/\d{2}/.*)"
)


def _build_movable_meta() -> dict[int, tuple[str | None, str | None]]:
    """Pre-index Pascha-relative delta → (url_id_slug, notes) from OCA scraped data.

    Scrape-year detection: tries to extract the year from the OCA URL of the Pascha
    entry (group 2 of _OCA_URL_DATE_RE). When the stored year is 0000 (year-neutral
    storage), falls back to searching years 2015–2050 for one where
    julian_pascha_as_gregorian(year) matches the Pascha entry's civil month/day.
    Notes are liturgically timeless and preserved as-is. URL date portions are
    stripped (only the stable id-slug tail is kept) and reconstructed at serve time.
    """
    from datetime import date as _d

    # Find the Pascha entry; derive the scrape year from the URL or by matching
    # the entry's month_day (civil Gregorian date) against computed Pascha dates.
    scrape_pascha: _d | None = None
    for entry in _INDEX.get("oca", []):
        for s in entry.saints:
            tl = (s.title or "").lower()
            if "pascha" in tl and is_movable_feast_title(s.title or ""):
                url = s.hagiography_url or ""
                m = _OCA_URL_DATE_RE.match(url)
                if m:
                    scrape_year = int(m.group(2))
                    if scrape_year > 0:
                        scrape_pascha = julian_pascha_as_gregorian(scrape_year)
                    else:
                        # Year stored as 0000 — find year by matching civil month/day
                        em, ed = (int(x) for x in entry.month_day.split("-"))
                        for candidate in range(2015, 2051):
                            p = julian_pascha_as_gregorian(candidate)
                            if p.month == em and p.day == ed:
                                scrape_pascha = p
                                break
                break
        if scrape_pascha:
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
                    id_slug = m.group(4) if m else None
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


def _build_oca_url(url: str | None, calendar_date: str | None) -> str | None:
    """Build an OCA URL by extracting the id-slug from *url* and using *calendar_date* for the date.

    The dataset stores full OCA URLs (with the 2024 scrape year and date), e.g.:
      https://www.oca.org/saints/lives/2024/01/02/100941-seraphim-of-sarov
    This function strips that stored date entirely — it extracts only the stable
    id-slug (the last path segment) and rebuilds the URL with the tradition's own
    calendar date:
      - Julian traditions: calendar_date is the Julian date
        (e.g. Serbian Christmas Gregorian Jan 7 2026 → "2025-12-25")
      - Revised-Julian / Gregorian traditions: calendar_date equals the
        Gregorian date (same as Julian until the 2800 divergence)
    Do NOT call this for movable feast saints — their OCA pages are keyed by
    the Gregorian feast date, which differs from Julian calendar_date.
    Non-OCA URLs (no regex match) are returned unchanged.
    """
    if not url or not calendar_date:
        return url
    m = _OCA_URL_DATE_RE.match(url)
    if not m:
        return url
    try:
        cal_year, cal_month, cal_day = calendar_date.split("-")
        return (
            f"https://www.oca.org/saints/lives/"
            f"{cal_year}/{int(cal_month):02d}/{int(cal_day):02d}/{m.group(4)}"
        )
    except (ValueError, AttributeError):
        return url


def _normalize_oca_url(url: str | None) -> str | None:
    """Replace the 0000 placeholder year in a stored OCA URL with an appropriate year.

    OCA hagiography pages are not year-specific for fixed feasts; substituting
    the current year produces a valid, working link without needing calendar context.
    Exception: Feb 29 only exists in leap years, so those URLs use 2024 (a known
    leap year) regardless of the current year.
    Non-OCA URLs or already-valid years are returned unchanged.
    """
    if not url:
        return url
    m = _OCA_ZERO_YEAR_RE.match(url)
    if not m:
        return url
    path = m.group(2)
    year = 2024 if path.startswith("02/29/") else date.today().year
    return f"{m.group(1)}{year}/{path}"


def _resolve_hagiography_url(saint: Saint, calendar_date: str | None = None) -> str | None:
    """Return the hagiography URL for the configured HAGIOGRAPHY_SOURCE.

    OCA URLs are fully rebuilt from the tradition's calendar date + the stored
    id-slug — no date from the static dataset is carried through.
    "goarch" → uses saint.goarch_url when set, then falls back to rebuilt OCA URL.
    """
    if HAGIOGRAPHY_SOURCE == "goarch":
        return saint.goarch_url or _build_oca_url(saint.hagiography_url, calendar_date)
    return _build_oca_url(saint.hagiography_url, calendar_date)


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
# Sentinel rank for a candidate matched only as a substring, so every such
# candidate sorts below any whole-word match without special-casing.
_NO_WHOLE_WORD_KEY = 1_000_000

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
    "of",
    "the",
}
# "great" is deliberately absent. The tokens above are honorifics applied to
# every saint, so dropping them helps two sources agree. "the Great" is an
# epithet that *identifies* one -- Basil, Anthony, Constantine -- and dropping
# it collapsed "Basil the Great" to the single token "basil", which then ranked
# behind any other Basil carrying more text.


def _normalize_saint_text(value: str) -> str:
    # Fold diacritics (e.g. "Șaguna" → "saguna", "Pčinja" → "pcinja") before
    # stripping non-ASCII so Romanian/Bulgarian saints remain findable with
    # plain ASCII queries.
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.category(c).startswith("M")
    )
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


# Calendar systems that use the Byzantine MM-DD space (Julian and Revised-Julian).
# The month_day parameter on /hagiography is documented as a Byzantine fixed-feast
# key, so non-Byzantine calendars (Coptic, Ethiopian) are excluded when it is set.
_BYZANTINE_CALENDARS: frozenset[CalendarSystem] = frozenset(
    {CalendarSystem.JULIAN, CalendarSystem.REVISED}
)

# Cache entry type: (search-keys, saint, month_day, calendar)
_CacheEntry = Tuple[frozenset[str], Saint, str, CalendarSystem]


@functools.lru_cache(maxsize=None)
def _get_hagio_cache() -> Tuple[_CacheEntry, ...]:
    """Build and return the hagiography lookup cache (built once, thread-safe via lru_cache).

    Groups all index entries by (month_day, calendar) — not just month_day —
    so saints from different calendar systems that share an identical MM-DD
    string (e.g. Coptic "01-01" vs Byzantine "01-01") are never merged together.

    Within each (month_day, calendar) group the same overlay-merge logic as
    _merge_entries is applied: first occurrence wins per field, later entries
    fill only missing values via _apply_overlay.  This ensures goarch_url and
    extended_notes from tradition overlays are visible to /hagiography.

    Returns a tuple (structurally immutable) of (keys, saint, month_day, calendar)
    4-tuples.  The contained Saint objects are shared across all callers and must
    be treated as read-only; mutating them would corrupt the cache for subsequent
    requests.  Use saint.model_copy() before making any field modifications.
    """
    # Group every raw entry by (month_day, calendar) across all traditions.
    by_md_cal: Dict[Tuple[str, CalendarSystem], List[CalendarEntry]] = {}
    for tradition_entries in _INDEX.values():
        for entry in tradition_entries:
            key = (entry.month_day, entry.calendar)
            by_md_cal.setdefault(key, []).append(entry)

    result: List[_CacheEntry] = []
    for (month_day, cal_sys), md_entries in by_md_cal.items():
        # Merge saints within the same (month_day, calendar) group.
        merged: Dict[str, Saint] = {}   # primary_key -> merged saint
        key_index: Dict[str, str] = {}  # any normalised key -> primary_key
        all_keys: Dict[str, set[str]] = {}  # primary_key -> all keys seen
        for entry in md_entries:
            for saint in entry.saints:
                keys = _saint_keys(saint)
                primary_key = next(
                    (key_index[k] for k in keys if k in key_index), None
                )
                if primary_key:
                    _apply_overlay(merged[primary_key], saint)
                    for k in keys:
                        key_index.setdefault(k, primary_key)
                        all_keys[primary_key].add(k)
                else:
                    primary_key = keys[0]
                    merged[primary_key] = saint.model_copy()
                    all_keys[primary_key] = set(keys)
                    for k in keys:
                        key_index[k] = primary_key

        for primary_key, saint in merged.items():
            result.append((frozenset(all_keys[primary_key]), saint, month_day, cal_sys))

    return tuple(result)


@functools.lru_cache(maxsize=None)
def _get_hagio_byzantine_index() -> Dict[str, Tuple[_CacheEntry, ...]]:
    """Pre-index Byzantine (Julian/Revised-Julian) cache entries by month_day.

    Built once from _get_hagio_cache() and cached. Reduces the month_day filter
    path in get_hagiography() from O(N) over the full cache to O(1) lookup + O(k)
    match scan where k = saints on that Byzantine date.

    Non-Byzantine calendars (Coptic, Ethiopian) are intentionally excluded: the
    month_day parameter is documented as a Byzantine fixed-feast MM-DD key, so
    Coptic/Ethiopian entries whose MM-DD string coincidentally matches are ignored.
    """
    index: Dict[str, List[_CacheEntry]] = {}
    for entry in _get_hagio_cache():
        _ks, _saint, month_day, cal = entry
        if cal in _BYZANTINE_CALENDARS:
            index.setdefault(month_day, []).append(entry)
    return {md: tuple(entries) for md, entries in index.items()}


def _apply_overlay(base: Saint, overlay: Saint) -> None:
    """Merge overlay fields into base saint in-place.

    Overlay entries carry tradition-specific canonization data and richer
    hagiography fields that the shared base dataset may lack.

    Priority: neobyzantine_hagiographies.json notes → extended_notes on the base
    (so they surface at /hagiography even when OCA notes already exist).
    neobyzantine_url and neobyzantine_actor_slug propagate when the overlay has them.

    Promoting notes into extended_notes is gated on the overlay carrying a known
    provenance (extended_notes_source, stamped at load time by data_loader, or
    neobyzantine cross-link metadata). Ordinary tradition overlays (Armenian,
    Serbian, ...) carry none, so their notes stay in notes: promoting them would
    both shadow the base OCA hagiography at /hagiography and be reported as
    source="goarch", which _format_hagiography_response assumes for any
    extended_notes with no source recorded.
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
    # Provenance of the overlay's hagiography text, or None for a plain tradition
    # overlay. data_loader stamps extended_notes_source on curated datasets; the
    # cross-link fields are the fallback signal for entries that carry them.
    overlay_source = overlay.extended_notes_source or (
        "neobyzantine"
        if (overlay.neobyzantine_actor_slug or overlay.neobyzantine_url)
        else None
    )
    # Only a provenance-tagged overlay may promote its notes to extended_notes —
    # that is what lets neobyzantine_hagiographies.json surface at /hagiography as
    # curated content without an untagged tradition overlay doing the same and
    # being mislabeled as GOARCH.
    if overlay_source and overlay.notes and not base.extended_notes:
        base.extended_notes = overlay.notes
        base.extended_notes_source = overlay_source
    if overlay.extended_notes and not base.extended_notes:
        base.extended_notes = overlay.extended_notes
        if overlay_source:
            base.extended_notes_source = overlay_source
    if overlay.canonized_by and not base.canonized_by:
        base.canonized_by = overlay.canonized_by
    if overlay.canonization_scope and not base.canonization_scope:
        base.canonization_scope = overlay.canonization_scope
    if overlay.year_canonized and not base.year_canonized:
        base.year_canonized = overlay.year_canonized
    # Cross-links to neobyzantine.org (populated when actor_slug is present in hagiographies JSON)
    if overlay.neobyzantine_url and not base.neobyzantine_url:
        base.neobyzantine_url = overlay.neobyzantine_url
    if overlay.neobyzantine_actor_slug and not base.neobyzantine_actor_slug:
        base.neobyzantine_actor_slug = overlay.neobyzantine_actor_slug


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
        # Movable feast URLs are keyed by the Gregorian feast date (injected by
        # get_saints_for_date/month with the correct date already).  Applying
        # _build_oca_url would replace that Gregorian date with the Julian
        # calendar_date, producing a wrong URL.  Skip the rewrite for them.
        if not is_movable_feast_title(s.title or ""):
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
            if any(is_movable_feast_title(s.title or "") for e in base_entries for s in e.saints):
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
    # Precompute once: which month_days in the OCA base have movable-feast saints
    # so the per-day filter is skipped on the vast majority of days that don't.
    oca_movable_month_days: set[str] = (
        {
            entry.month_day
            for entry in _INDEX.get(base_key, [])
            if any(is_movable_feast_title(s.title or "") for s in entry.saints)
        }
        if base_key == "oca"
        else set()
    )

    result: Dict[str, Any] = {}
    for day_num in range(1, _cal.monthrange(year, month)[1] + 1):
        d = date(year, month, day_num)
        month_day, calendar_date = convert_to_tradition_month_day(d, tradition)
        cal = effective_calendar(d, tradition)

        base_day = list(base_by_md.get(month_day, []))
        overlay_day = list(overlay_by_md.get(month_day, [])) if overlay_by_md else []

        if cal in (CalendarSystem.JULIAN, CalendarSystem.REVISED) and base_key == "oca":
            if month_day in oca_movable_month_days:
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


def get_hagiography(saint_name: str, month_day: Optional[str] = None) -> HagiographyResponse:
    """Find a saint by name (and optionally MM-DD) and return hagiography data.

    Searches across all traditions using a lazy-initialised cache (built on
    first call via _get_hagio_cache()). If month_day is given, only saints on
    that date are considered;
    no fallback to a full scan is performed so the parameter acts as a true filter.
    Among all name matches, selects the best candidate by field priority
    (extended_notes > notes > hagiography_url), with month_day + name as a
    stable tie-breaker to ensure deterministic results across dataset changes.
    """
    original_name = saint_name
    saint_name = saint_name.strip()
    if not saint_name:
        # Echo the original (pre-strip) value so clients can correlate the response.
        return HagiographyResponse(saint=original_name, source="not_found")

    # Normalize the query directly via _normalize_saint_text (drops honorifics,
    # stop-words, punctuation) rather than routing through _saint_keys, which
    # falls back to the raw lowercased input when all tokens are dropped — that
    # fallback causes honorific-only queries like "saint" or "st" to match broadly.
    normalized_query = _normalize_saint_text(saint_name)
    q_tokens = [t for t in normalized_query.split() if len(t) >= 2]
    if not q_tokens:
        # Nothing searchable survived normalization (e.g. "st", "saint", "the").
        # Raise ValueError; the route handler translates this to HTTP 422.
        raise ValueError("saint name contains no searchable tokens after normalization")

    def _matches_whole_word(entry_keys: frozenset[str]) -> bool:
        """Every query token appears as a whole word in some key."""
        return all(
            any(qt in sk.split() for sk in entry_keys)
            for qt in q_tokens
        )

    def _matches(entry_keys: frozenset[str]) -> bool:
        """Every query token appears anywhere in some key, substring included.

        Kept as the fallback tier so partial and inflected queries still resolve.
        On its own it is too loose to rank on: keys are normalized to bare words,
        so the token "basil" is a substring of "cabasilas" and of "basilisk", and
        a query for Basil the Great returned Nicholas Cabasilas -- a confident
        answer about a different saint.
        """
        return all(any(qt in sk for sk in entry_keys) for qt in q_tokens)

    _query_tokens = frozenset(q_tokens)

    def _extra_tokens(entry_keys: frozenset[str]) -> int:
        """How many tokens beyond the query the tightest whole-word key carries.

        A composite commemoration ("Synaxis of the Three Hierarchs: Basil the
        Great, Gregory the Theologian, & John Chrysostom") contains the query as
        a subset just as the saint's own entry does, and carries more text, so
        ranking on text alone handed the query to the composite. Preferring the
        tightest key picks the entry that is *about* the saint asked for.

        Substring-tier candidates have no whole-word key and all score equally,
        leaving their relative order to the tie-breakers below.
        """
        extras = [
            len(toks - _query_tokens)
            for toks in (frozenset(sk.split()) for sk in entry_keys)
            if _query_tokens <= toks
        ]
        return min(extras) if extras else _NO_WHOLE_WORD_KEY

    # Carry (ks, saint, month_day) tuples so _best can use month_day as a
    # deterministic tie-breaker without re-indexing.
    def _best(candidates: List[tuple[frozenset[str], Saint, str]]) -> Optional[Saint]:
        if not candidates:
            return None
        _, saint, _ = max(
            candidates,
            key=lambda t: (
                -_extra_tokens(t[0]),  # closest name first, before text richness
                bool(t[1].extended_notes),
                bool(t[1].notes),
                "oca.org" in (t[1].hagiography_url or ""),  # prefer OCA-backed entries
                bool(t[1].hagiography_url),
                t[2],       # month_day: stable lexicographic sort
                t[1].name,  # name: final stable tie-breaker
            ),
        )
        return saint

    def _select(entries) -> List[tuple[frozenset[str], Saint, str]]:
        """Whole-word matches if there are any, else the looser substring tier.

        Two tiers rather than one so precision does not cost recall: an exact
        name resolves to that saint, while a partial query that matches nothing
        as a whole word still falls back to substring matching.
        """
        whole = [
            (ks, s, md) for (ks, s, md, _cal) in entries if _matches_whole_word(ks)
        ]
        if whole:
            return whole
        return [(ks, s, md) for (ks, s, md, _cal) in entries if _matches(ks)]

    if month_day:
        # Use the pre-indexed Byzantine-only lookup: O(1) dict access + O(k) match
        # scan where k = saints on that Byzantine date.  Non-Byzantine calendars
        # (Coptic, Ethiopian) are excluded because month_day is documented as a
        # Byzantine fixed-feast MM-DD key.
        byzantine_entries = _get_hagio_byzantine_index().get(month_day, ())
        found = _best(_select(byzantine_entries))
        if found:
            return _format_hagiography_response(found)
        # month_day given but no match on that date — treat as not found rather
        # than silently falling through to a full scan that may return a different saint.
        return HagiographyResponse(saint=saint_name, source="not_found")

    found = _best(_select(_get_hagio_cache()))
    if found:
        return _format_hagiography_response(found)

    return HagiographyResponse(saint=saint_name, source="not_found")


def _hagio_url(saint: Saint) -> str | None:
    """Return the hagiography URL for the response, respecting HAGIOGRAPHY_SOURCE.

    OCA URLs with placeholder year 0000 are normalized to the current year for
    fixed-feast saints. Movable-feast saints have year-dependent month/day in
    their stored URLs, so normalization would produce a wrong date — their URLs
    are omitted (None) to avoid serving a broken link.
    """
    if HAGIOGRAPHY_SOURCE == "goarch" and saint.goarch_url:
        return saint.goarch_url
    if is_movable_feast_title(saint.title or saint.name or ""):
        return None
    return _normalize_oca_url(saint.hagiography_url)


def _format_hagiography_response(saint: Saint) -> HagiographyResponse:
    hagiography = saint.extended_notes or saint.notes
    oca_url = saint.hagiography_url or ""
    # Source reflects the text actually returned.
    # OCA dataset stores hagiography text in notes alongside an oca.org URL;
    # check the URL hostname so those entries report source=oca, not notes.
    if saint.extended_notes:
        source = saint.extended_notes_source or "goarch"
    elif saint.notes and saint.extended_notes_source:
        # A curated dataset stamps provenance at load time, so its text is
        # attributable whether or not a merge promoted it into extended_notes.
        # Without this the same neobyzantine entry reported "neobyzantine" when
        # it overlaid an OCA saint and "notes" when it stood alone.
        source = saint.extended_notes_source
    elif saint.notes and "oca.org" in oca_url:
        source = "oca"
    elif saint.notes:
        source = "notes"
    else:
        # No local text — source reflects the hagiography field, not URL presence
        source = "not_found"
    return HagiographyResponse(
        saint=saint.title or saint.name,
        hagiography=hagiography,
        goarch_url=saint.goarch_url,
        hagiography_url=_hagio_url(saint),
        source=source,
    )
