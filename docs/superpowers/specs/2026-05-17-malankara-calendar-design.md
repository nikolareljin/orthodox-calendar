# Malankara Orthodox Calendar — Import Design

**Date:** 2026-05-17  
**Branch:** feat/data-import-phase1  
**Status:** Approved

---

## Goal

Add a dedicated `malankara_saints.json` dataset for the Malankara Orthodox Syrian Church (MOSC), replacing the temporary `data_key="oriental"` fallback in `config.py`. Update Malankara's calendar system from Julian to Gregorian (MOSC adopted the Gregorian calendar in 1953).

---

## Context

`malankara` is already defined as a tradition in `config.py` and `traditions.js` (frontend). No dedicated saints dataset exists — it currently falls back to `oriental_saints.json` (only 6 entries). This design covers building a comprehensive Malankara dataset from multiple authoritative sources.

---

## Calendar System

**Key fact:** The Malankara Orthodox Syrian Church switched from the Julian to the Gregorian calendar in 1953.  
Source: https://talmido.org/index.php?title=Liturgical_Calendar

**Impact:**
- `config.py`: Change `malankara` from `CalendarSystem.JULIAN` → `CalendarSystem.GREGORIAN`
- `config.py`: Remove `data_key="oriental"` (dedicated dataset replaces the fallback)
- Dataset keys: store Gregorian `MM-DD` values
- Shared Syriac saints: require Julian → Gregorian conversion (−13 days in 21st century)

---

## Files Changed

| File | Change |
|---|---|
| `scripts/import_malankara.py` | New — multi-source importer script |
| `backend/app/data/traditions/malankara_saints.json` | New — generated output (not hand-written) |
| `backend/app/config.py` | Update `malankara` entry: `JULIAN→GREGORIAN`, remove `data_key` |

No model changes (`Saint`, `CalendarEntry` already sufficient).  
No frontend changes (`malankara` already in `traditions.js`).

---

## Data Sources

| Priority | Source | Format | Date handling |
|---|---|---|---|
| 1 (base) | Google Calendar Malankara ICS | ICS | Gregorian — use as-is |
| 2 | Syriac Patriarchate ICS 2026 (`dss-syriacpatriarchate.org`) | ICS | Julian civil → subtract 13 days |
| 3 | Panjangom 2025 PDF (`mosc.in`) | PDF | pdfplumber extraction |
| 4 | `syriacorthodoxresources.org/Calendar/` | HTML | Julian → subtract 13 days |
| 5 | `mosc-temp.com/mosc-redesign/the-church/church-calendar` | HTML | Gregorian — use as-is |
| 6 | Wikipedia | API | Enrichment only |
| 7 (optional) | Farley Lawrence synaxarion (Scribd) | Manual PDF | If automated coverage is insufficient |

**Julian → Gregorian conversion:** `gregorian_date = julian_civil_date - timedelta(days=13)`  
(Offset is constant at 13 days for all dates in the 21st century.)

---

## Script Design

```
scripts/import_malankara.py
```

### CLI flags

```
--out PATH          Output path (default: backend/app/data/traditions/malankara_saints.json)
--no-ics            Skip Google Calendar ICS phase
--no-syriac-ics     Skip Syriac Patriarchate ICS phase
--no-pdf            Skip Panjangom PDF phase
--no-syriac-web     Skip syriacorthodoxresources.org phase
--no-mosc-web       Skip mosc-temp.com phase
--no-enrich         Skip Wikipedia enrichment
--dry-run           Print summary, write nothing
--merge             Merge into existing file instead of replacing
```

### Processing pipeline

```
Phase 1 — Google Calendar Malankara ICS
  → fetch ICS from calendar ID
  → parse DTSTART (Gregorian) + SUMMARY
  → filter noise (ordinal-day entries, bare fast markers)
  → base entry set

Phase 2 — Syriac Patriarchate ICS 2026
  → fetch dss-syriacpatriarchate.org ICS
  → parse DTSTART + SUMMARY
  → subtract 13 days (Julian civil → Malankara Gregorian)
  → merge: add new saints, enrich existing

Phase 3 — Panjangom PDF
  → download mosc.in PDF
  → pdfplumber text extraction
  → regex: date pattern + saint name
  → normalize to MM-DD
  → merge

Phase 4 — syriacorthodoxresources.org
  → GET calendar page
  → BeautifulSoup parse
  → extract date + saint pairs
  → subtract 13 days
  → merge

Phase 5 — mosc-temp.com
  → GET church-calendar page
  → BeautifulSoup parse
  → extract date + saint pairs (Gregorian)
  → merge

Phase 6 — Wikipedia enrichment
  → same approach as import_armenian_ics.py
  → fetch extracts for cleaned saint names
  → add hagiography_url and notes where absent

→ Write malankara_saints.json
```

### Merge rule

Normalize saint name (strip honorifics, punctuation, stop words) → match key → overlay empty fields only. No overwrite of already-populated fields. Same algorithm as `services/saints.py:_normalize_saint_text`.

### Output format

```json
[
  {
    "month_day": "01-07",
    "tradition": "malankara",
    "calendar": "gregorian",
    "saints": [
      {
        "name": "Nativity of Our Lord Jesus Christ",
        "title": "Nativity of Our Lord Jesus Christ",
        "feast_type": "Feast",
        "hagiography_url": null,
        "notes": "Major feast of the Malankara Orthodox Syrian Church.",
        "canonized_by": null,
        "canonization_scope": "universal",
        "year_canonized": null
      }
    ]
  }
]
```

---

## Feast Type Detection

Reuse existing `_FEAST_TYPE_RULES` regex patterns (Martyr, Hieromartyr, Venerable, Apostle, etc.).  
Add Malankara-specific feast markers: `perunnal`, `thirunal` → `"Feast"`.

---

## Error Handling

- Each phase is independently skippable and failure-tolerant
- Network/fetch error per phase: `WARN` to stderr, continue remaining phases
- PDF parse failure: `WARN`, skip PDF phase (non-fatal)
- Wikipedia batch error: `WARN`, continue with remaining batches
- Final output validated against Pydantic `CalendarEntry` before write

---

## Scope Excluded

- Lectionary readings (scripture passages) — out of scope; no readings field in current data model
- Malayalam script names — no bilingual field exists; `name_hy` is Armenian-specific
- Model changes — existing `Saint` fields sufficient

---

## Dependencies

New Python dependencies required:
- `pdfplumber` — PDF text extraction (not currently in `requirements.txt`)
- `beautifulsoup4` + `lxml` — HTML parsing (check if already present)

---

## Validation

After import:
1. Spot-check output JSON for date accuracy (verify Christmas = `12-25`, not `01-07`)
2. Run existing `backend/tests/test_api_smoke.py`
3. Manually query `/api/saints?date=YYYY-12-25&tradition=malankara` to verify data loads

---

## Optional Supplemental Source

**Farley Lawrence synaxarion** (`scribd.com/document/925773545`): "A Daily Calendar of Saints — a Synaxarion for Today's North American Church". Scribd requires authentication — not automatable. If automated phases produce insufficient coverage, manually download and add saints from this PDF as a supplemental pass.
