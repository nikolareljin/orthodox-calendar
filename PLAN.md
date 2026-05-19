# Orthodox Calendar — Data Sources & Import Pipeline Plan

## Context

The `orthodox-calendar` project (`/home/nikos/Projects/orthodox-calendar`) currently serves 2,970 Byzantine saints across 16 traditions from pre-built JSON files. The base dataset comes from `orthocal.info` (via `scripts/import_orthocal.py`). However, several traditions are critically under-populated:

- **Syriac Orthodox, Malankara, Assyrian** — share the generic `oriental` data key; no tradition-specific saints at all
- **Armenian, Ethiopian, Coptic** — minimal hand-curated overlays (a few dozen saints each)
- **Individual Patriarchates** (Serbian, Russian, Greek, Georgian, Romanian, Bulgarian) — tiny overlays, missing locally-canonized saints
- **Hagiographies** — only short excerpts (`notes` field, 500 chars). `neobyzantine_hagiographies.json` exists but is unused in the API.
- **GOARCH** — hagiography URLs are hard-coded links; no automated import of full saint texts.

Goal: design a comprehensive, maintainable data acquisition pipeline covering all gaps.

---

## Part 1 — Oriental Orthodox Churches

### 1.1 Coptic Orthodox Church

**Best source: `coptic.io` API** — open-source, MIT licensed, TypeScript/GraphQL, maintained.

| Endpoint | Data |
|---|---|
| `GET https://api.coptic.io/synaxarium/:gregorianDate` | Saints for a Gregorian date (returns Coptic saints with Coptic date) |
| `GET https://api.coptic.io/synaxarium/coptic/:copticDate` | Saints by Coptic calendar date |
| `GET https://api.coptic.io/synaxarium/search/query?q=` | Search saints by name |
| `GET https://api.coptic.io/calendar/ical/subscribe` | iCal feed |

**Secondary source: `st-takla.org/Synaxarium/`** — already planned in `scripts/README.md`. Has the full Coptic Synaxarium in English and Arabic.

**Readings source: `katameros-api`** (`github.com/pierresaid/katameros-api`) — daily readings in EN/FR/AR/IT.

**Action:**
1. Write `scripts/import_coptic.py`:
   - Iterates all Coptic calendar days (30 days × 13 months = 390 days, with leap day in month 13)
   - Calls `api.coptic.io/synaxarium/:date` for each Gregorian day of a full year
   - Maps Coptic feast types → `feast_type` enum
   - Outputs `backend/app/data/traditions/coptic_saints.json` (full replacement of hand-curated file)
   - Includes `hagiography_url` pointing to coptic.io or st-takla.org per saint
2. Calendar note: Coptic year starts ~September 11/12 Gregorian; Coptic months need mapping to Julian/Gregorian dates.

---

### 1.2 Syriac Orthodox Church

**No API exists.** Best web sources:
- `syriacorthodoxresources.org/Calendar/` — annual liturgical calendar (HTML)
- `soc-wus.org/Calendar.htm` — Archdiocese of Western US monthly calendar
- `morefrem.com/syriac-orthodox-calendar/` — parish-level

**Strategy: Playwright scraper** (HTML is structured enough for extraction)

**Action:**
1. Write `scripts/import_syriac.py` with Playwright:
   - Navigate `syriacorthodoxresources.org/Calendar/` monthly pages
   - Extract saint names, feast ranks, dates
   - Assign `canonization_scope: "oriental"`, `canonized_by: "Syriac Orthodox Church"`
   - Output `backend/app/data/traditions/syriac_saints.json`
   - Add new data key `"syriac"` in `config.py`
2. Update `config.py`: Syriac tradition gets `data_key: "syriac"` (currently shares "oriental")

---

### 1.3 Malankara Orthodox Syrian Church

**No API exists.** Sources:
- `malankara.com/lectionary` — lectionary (readings focus)
- `mosc.in/the_church/liturgy/liturgical-year-seasons/` — official liturgical year description
- Downloadable PDF calendar (annual)

**Strategy: PDF parsing + Playwright**

**Action:**
1. Write `scripts/import_malankara.py`:
   - Download annual calendar PDF from `mosc.in`
   - Use `pdfplumber` or `pypdf` to extract saint entries
   - Fallback: Playwright scrape of `mosc.in` liturgical pages
   - Output `backend/app/data/traditions/malankara_saints.json`
   - Add `data_key: "malankara"` in `config.py`

---

### 1.4 Armenian Apostolic Church

**No API.** Sources:
- `armenianchurch.org/en/Liturgical-Calendar/` — official calendar (HTML, downloadable)
- `armenianprelacy.org/feast-days/` — feast days list
- `armenianchurch.us` — already in `traditions.js` as the US diocese

**Calendar note:** Armenian church uses its own calendar with ~160 fasting days. Saints commemorated Mon/Tue/Thu/Sat. Unique structure.

**Action:**
1. Write `scripts/import_armenian.py`:
   - Playwright scrape of `armenianprelacy.org/feast-days/`
   - Extract annual feast calendar with saint names and feast ranks
   - Map Armenian calendar dates → Julian/Gregorian (most feasts are fixed in Gregorian)
   - Expand `backend/app/data/traditions/armenian_saints.json` (currently ~5 saints → full annual calendar)

---

### 1.5 Ethiopian Orthodox Tewahedo Church

**No API.** Sources:
- `ethiopianorthodox.org/english/calendar.html` — official English calendar
- Ethiopian calendar: 13 months (12 × 30 days + 1 × 5/6 days "Pagumē")
- Year starts Meskerem 1 = ~September 11/12 Gregorian
- Each of the 4 Evangelists has a leap year cycle

**Unique challenge:** Ethiopian Ge'ez language hagiographies. English translations exist but are sparse.

**Action:**
1. Write `scripts/import_ethiopian.py`:
   - Playwright scrape of `ethiopianorthodox.org/english/calendar.html`
   - Build Ethiopian→Gregorian date mapping utility (add to `calendar_logic.py`)
   - Extract saints (Kidus/Kidist = male/female saint prefix in Ge'ez)
   - Key Ethiopian saints: Gebre Menfes Qiddus, Tekle Haymanot, Yared (hymnographer), etc.
   - Output `backend/app/data/traditions/ethiopian_saints.json` (expand from ~5 entries)

---

### 1.6 Assyrian Church of the East

**No data currently.** Sources:
- `calendar.assyrianchurch.org/` — official liturgical calendar with English and Arabic/Assyrian versions
- `acote.church/ecclesiastical-calendar` — Diocese of Western Europe

**Calendar note:** Assyrian church uses East Syriac liturgical calendar; feasts differ from Western Syriac (Syriac Orthodox).

**Action:**
1. Write `scripts/import_assyrian.py`:
   - Playwright scrape of `calendar.assyrianchurch.org/english-liturgical-calendar/`
   - Extract 12 months of feast days and saint commemorations
   - Add `data_key: "assyrian"` in `config.py` (currently returns empty)
   - Output `backend/app/data/traditions/assyrian_saints.json`

---

## Part 2 — Eastern Orthodox Patriarchates

Current state: all Eastern Orthodox traditions share `oca_julian.json` as base. Overlays exist but are minimal (a few saints each).

### 2.1 Russian Orthodox Church (Moscow Patriarchate)

**No official API from patriarchia.ru.**

**Sources:**
- `orthocal.info/api/julian/` — already used; includes some Russian saints
- `holytrinityorthodox.com/calendar/rss/saints.htm` — RSS feed with daily saints (Julian calendar)
- Holy Trinity Monastery (ROCOR) calendar — comprehensive New Martyrs and Confessors lists
- `days.pravoslavie.ru` (Pravoslavie.ru) — major Russian Orthodox calendar website with hagiographies (Russian language)

**Key missing saints:** New Martyrs of Russia (canonized 1988–2000+), ~1,800 saints. Many not in `orthocal.info`.

**Action:**
1. Parse Holy Trinity RSS feed: `holytrinityorthodox.com/calendar/rss/saints.htm`
   - Write `scripts/import_russian.py` using `feedparser`
   - Collect saints not already in base dataset
   - Tag `canonized_by: "Russian Orthodox Church"`, `canonization_scope: "local"`
2. Optionally scrape `days.pravoslavie.ru` for New Martyrs list (Russian text; may need translation)
3. Expand `russian_saints.json` significantly

---

### 2.2 Serbian Orthodox Church

**No official API.**

**Sources:**
- `crkvenikalendar.com/index_en.php` — "Eternal Orthodox Calendar" with English interface; Julian calendar
- `easterndiocese.org/calendar.html` — Eastern American Diocese calendar
- `svetosavlje.org` — comprehensive Serbian Orthodox resource with hagiographies (Serbian)
- `spc.rs` — official Serbian Patriarchate (Serbian language)

**Key missing saints:** Serbian New Martyrs (WWII), Holy Prince Lazar, Serbian medieval saints, Hilandar monks.

**Action:**
1. Write `scripts/import_serbian.py`:
   - Playwright scrape of `crkvenikalendar.com` (English available)
   - 366 days, extract Serbian-specific commemorations not in base dataset
   - Tag `canonized_by: "Serbian Orthodox Church"`
2. Expand `serbian_saints.json`

---

### 2.3 Greek Orthodox Archdiocese / Ecumenical Patriarchate (GOARCH)

**This is the richest source — see Part 3 for full GOARCH import plan.**

**Additional API: `orthodoxcalendar.xyz`**
- Programmatic interface for GOARCH liturgical calendar
- Returns JSON, supports ICS format
- Endpoint pattern: `GET https://orthodoxcalendar.xyz/api/calendar/{date}`

**Action:**
1. Investigate `orthodoxcalendar.xyz` API schema (see Part 3 for full GOARCH strategy)
2. Expand `greek_saints.json` with Ecumenical Patriarchate canonizations (20th century saints)

---

### 2.4 Romanian Orthodox Church

**No API.** Adopted Revised Julian Calendar 1924. Sources:
- `patriarhia.ro` — official (Romanian language)
- `roea.orthodoxws.com/calendar.html` — Romanian Episcopate of America

**Key saints:** Romanian New Martyrs of Communist persecution (canonized 2007+), Ancient Dacian martyrs.

**Action:**
1. Write `scripts/import_romanian.py`:
   - Playwright scrape of Romanian Episcopate calendar
   - Focus on Romania-specific canonizations
2. Create `backend/app/data/traditions/romanian_saints.json` (does not exist yet)

---

### 2.5 Bulgarian Orthodox Church

**No API.** Adopted Revised Julian Calendar 1968. Sources:
- `bg-patriarshia.bg` — official (Bulgarian language)
- Various diaspora parish websites in English

**Key saints:** Bulgarian New Martyrs, medieval saints (Saints of the Bulgarian National Revival), St. John of Rila.

**Action:**
1. Create `backend/app/data/traditions/bulgarian_saints.json` (does not exist yet)
2. Manual curation initially; scraper later if English source found

---

### 2.6 Georgian Orthodox Church

**No API.** Uses Julian calendar (did not adopt Revised). Sources:
- `patriarchate.ge` — official (Georgian language)
- Georgian saints are partially in `orthocal.info` dataset

**Key saints:** St. Nino (Equal to the Apostles), St. David of Gareji, Georgian Royal Saints.

**Action:**
1. Expand `backend/app/data/traditions/georgian_saints.json` (exists, minimal)
2. Manual curation for major Georgian saints; scraper if English source found

---

## Part 3 — GOARCH Full Import Strategy

### The Problem

GOARCH (`goarch.org/chapel/saints`) has the most comprehensive English-language hagiographies for Greek Orthodox saints. Currently, only a few dozen are manually linked via `hagiography_url` in our data. We need all 366 days of saint hagiographies.

### Option A: Playwright Scraper (Recommended)

**Approach:**
1. Navigate `https://www.goarch.org/chapel/calendar` for each month
2. Extract all saint names and their individual saint page URLs
3. For each saint URL (e.g., `goarch.org/chapel/saints?contentid=123&contentdate=2024-01-07`):
   - Extract: full name, feast type, hagiography text, troparion, kontakion, icon reference
   - Store full hagiography text locally (not just URL)
4. Match GOARCH saints to our existing saints in `oca_julian.json` by name normalization
5. Enrich matched saints with `hagiography_url` and extended `notes`

**Rate limiting:** 1-2 seconds between requests, respect `robots.txt`

**Output format:**
```json
{
  "month_day": "01-07",
  "goarch_saints": [
    {
      "name": "Saint John the Baptist",
      "goarch_url": "https://www.goarch.org/chapel/saints?contentid=...",
      "hagiography": "Full text...",
      "troparion": "...",
      "kontakion": "...",
      "feast_type": "Great Feast"
    }
  ]
}
```

**Files to create:**
- `scripts/import_goarch.py` — Playwright-based scraper
- `backend/app/data/goarch_hagiographies.json` — output (new file, ~5-10 MB)
- Update `data_loader.py` to merge GOARCH hagiographies into API responses

### Option B: orthodoxcalendar.xyz API

**Approach:**
- `orthodoxcalendar.xyz` wraps GOARCH data programmatically
- Cleaner than scraping; JSON output
- Risk: third-party service, may go down; uncertain data completeness
- Use as **validation/supplement** to Playwright scraper

### Option C: Email Feed / Newsletter

**Assessment:** GOARCH sends daily saint commemorations via email. However:
- Email parsing is fragile (HTML newsletters)
- Requires subscribing and capturing 366+ emails
- No structured data extraction
- **NOT recommended** as primary strategy

**Verdict: Option A (Playwright) is the right approach.** Option B as fallback/validation.

### GOARCH Import Script Design

```python
# scripts/import_goarch.py
# Usage: python3 scripts/import_goarch.py --year 2024 --delay 2.0 --out backend/app/data/goarch_hagiographies.json

async def scrape_goarch_calendar(year: int, delay: float) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        results = []
        for month in range(1, 13):
            # 1. Get calendar page for month
            await page.goto(f"https://www.goarch.org/chapel/calendar?month={month}&year={year}")

            # 2. Extract saint links for each day
            saint_links = await page.eval_on_selector_all("a.saint-link", ...)

            # 3. For each saint, fetch individual page
            for link in saint_links:
                await page.goto(link["href"])
                saint_data = await extract_saint_data(page)
                results.append(saint_data)
                await asyncio.sleep(delay)

        return results
```

---

## Part 4 — Schema & Backend Updates

### 4.1 New Data Keys in `config.py`

Add:
- `"syriac"` — Syriac Orthodox (currently shares "oriental")
- `"malankara"` — Malankara Orthodox (currently shares "oriental")
- `"assyrian"` — Assyrian Church of the East (currently empty)
- `"coptic"` — Coptic Orthodox (extract from shared "oriental")

### 4.2 New JSON Files to Create

| File | Source | Method |
|---|---|---|
| `traditions/syriac_saints.json` | syriacorthodoxresources.org | Playwright |
| `traditions/malankara_saints.json` | mosc.in | Playwright + PDF |
| `traditions/assyrian_saints.json` | calendar.assyrianchurch.org | Playwright |
| `traditions/romanian_saints.json` | roea.orthodoxws.com | Playwright |
| `traditions/bulgarian_saints.json` | Manual curation | Manual |
| `goarch_hagiographies.json` | goarch.org | Playwright |

### 4.3 Expand Existing Files

| File | Current Saints | Target |
|---|---|---|
| `traditions/coptic_saints.json` | ~10 | Full Coptic synaxarium (300+) via coptic.io |
| `traditions/armenian_saints.json` | ~5 | Annual Armenian calendar (~100+) |
| `traditions/ethiopian_saints.json` | ~5 | Ethiopian Synaxarium (~200+) |
| `traditions/russian_saints.json` | ~5 | New Martyrs + major saints (~200+) |
| `traditions/serbian_saints.json` | ~8 | Serbian saints full calendar (~50+) |
| `traditions/georgian_saints.json` | ~3 | Key Georgian saints (~20+) |
| `traditions/greek_saints.json` | ~10 | GOARCH-specific saints (~50+) |

### 4.4 API Changes in `main.py` / `data_loader.py`

1. **New endpoint:** `GET /api/v1/hagiography?saint=<name>&date=<date>&tradition=<tradition>`
   - Returns full hagiography text from `goarch_hagiographies.json`
   - Falls back to `notes` field if not found

2. **Integrate** `neobyzantine_hagiographies.json` into `/api/v1/saints` response:
   - Currently loaded but unused
   - Merge into saints response as `extended_notes` field

3. **New import for GOARCH:** `data_loader.py` needs to load `goarch_hagiographies.json` and merge hagiography text into saint records by name matching

---

## Part 5 — Implementation Priority & Phasing

### Phase 1 — High-Impact, Easy (API-based)
1. **Coptic via coptic.io** — proper API, clean JSON, high-value data
2. **Russian via RSS** — structured RSS feed, `feedparser` library, no Playwright needed
3. **Greek via orthodoxcalendar.xyz** — investigate API, potentially no scraping

### Phase 2 — Medium effort (Playwright scrapers)
4. **GOARCH hagiographies** — highest priority for content quality
5. **Syriac Orthodox** — `syriacorthodoxresources.org` has clean HTML
6. **Assyrian** — `calendar.assyrianchurch.org` has structured pages
7. **Armenian** — `armenianprelacy.org/feast-days/`
8. **Serbian** — `crkvenikalendar.com` has English version

### Phase 3 — Complex (calendar system work required)
9. **Ethiopian** — needs Ethiopian calendar conversion utility
10. **Malankara** — needs PDF parsing or complex HTML scraping
11. **Romanian/Bulgarian** — language barrier; manual curation may be needed

### Phase 4 — Integration
12. Activate `neobyzantine_hagiographies.json` in API
13. New hagiography endpoint
14. Name-normalization utility for cross-source saint matching

---

## Part 6 — New Dependencies Needed

```
# requirements additions (backend)
playwright        # async HTML scraping (GOARCH, Syriac, Assyrian, Armenian, Serbian)
feedparser        # RSS feed parsing (Russian Orthodox)
pdfplumber        # PDF calendar parsing (Malankara)
httpx             # async HTTP for coptic.io API (replaces urllib in new scripts)
```

```
# New scripts
scripts/import_goarch.py        # Playwright — GOARCH hagiographies
scripts/import_coptic.py        # coptic.io API — full Coptic synaxarium
scripts/import_syriac.py        # Playwright — Syriac Orthodox calendar
scripts/import_assyrian.py      # Playwright — Assyrian liturgical calendar
scripts/import_armenian.py      # Playwright — Armenian Apostolic feast days
scripts/import_ethiopian.py     # Playwright — Ethiopian Orthodox calendar
scripts/import_russian.py       # RSS parser — Russian Orthodox saints/New Martyrs
scripts/import_serbian.py       # Playwright — Serbian Orthodox saints
scripts/import_malankara.py     # PDF/Playwright — Malankara calendar
```

---

## Part 7 — Open Questions

1. **st-takla.org vs coptic.io**: Which is more complete for Coptic hagiographies? st-takla.org has longer texts; coptic.io has cleaner API. Strategy: use coptic.io for saint list + feast data; scrape st-takla.org for full hagiography texts.

2. **Language handling**: Serbian, Russian, Georgian, Armenian, Ethiopian sources are primarily in local languages. Do we want:
   - English-only (use diaspora/American diocese websites only)?
   - Or store original-language text alongside English translations?

3. **GOARCH robots.txt**: Need to verify scraping is permitted before building the Playwright importer.

4. **orthodoxcalendar.xyz**: Is this a maintained service? Need to check uptime/reliability before depending on it.

5. **coptic.io API uptime**: Open-source project; need to check if actively hosted or self-host from GitHub source.

6. **Data refresh cadence**: Saints calendars are mostly stable year-over-year, but new canonizations happen. Should import scripts run annually via CI (GitHub Actions)?

---

## Files to Touch

| File | Change |
|---|---|
| `backend/app/config.py` | Add `syriac`, `malankara`, `assyrian`, `coptic` as distinct data keys |
| `backend/app/data_loader.py` | Load `goarch_hagiographies.json`; activate neobyzantine hagiographies |
| `backend/app/main.py` | New `/api/v1/hagiography` endpoint |
| `backend/app/models.py` | Add `extended_notes`, `goarch_hagiography` fields to `Saint` |
| `backend/app/calendar_logic.py` | Add Ethiopian calendar conversion utilities |
| `backend/requirements.txt` | Add `playwright`, `feedparser`, `pdfplumber`, `httpx` |
| `scripts/import_goarch.py` | New — Playwright GOARCH scraper |
| `scripts/import_coptic.py` | New — coptic.io API importer |
| `scripts/import_syriac.py` | New — Playwright Syriac scraper |
| `scripts/import_assyrian.py` | New — Playwright Assyrian scraper |
| `scripts/import_armenian.py` | New — Playwright Armenian scraper |
| `scripts/import_ethiopian.py` | New — Playwright Ethiopian scraper |
| `scripts/import_russian.py` | New — RSS Russian saints importer |
| `scripts/import_serbian.py` | New — Playwright Serbian scraper |
| `scripts/import_malankara.py` | New — PDF/Playwright Malankara importer |
| `backend/app/data/traditions/syriac_saints.json` | New data file |
| `backend/app/data/traditions/malankara_saints.json` | New data file |
| `backend/app/data/traditions/assyrian_saints.json` | New data file |
| `backend/app/data/traditions/romanian_saints.json` | New data file |
| `backend/app/data/traditions/bulgarian_saints.json` | New data file |
| `backend/app/data/goarch_hagiographies.json` | New data file (~5-10 MB) |
| `scripts/README.md` | Document all new import scripts |

---

## Part 8 — Full Localization Plan (Future)

> **Status:** Not for current implementation. Architectural notes only. When ready, implement after all English data sources are stable.

### 8.1 Languages Needed Per Tradition

| Tradition | Primary Language(s) | Script | Notes |
|---|---|---|---|
| Greek (Ecumenical Patriarchate) | Greek (Ελληνικά) | Greek | Official language of Patriarchate |
| Russian (Moscow Patriarchate) | Russian (Русский) | Cyrillic | Church Slavonic for liturgical texts |
| Serbian | Serbian (Српски) | Cyrillic + Latin | Both scripts in use; Church Slavonic liturgical |
| Romanian | Romanian (Română) | Latin | Uses diacritics: ă â î ș ț |
| Bulgarian | Bulgarian (Български) | Cyrillic | |
| Georgian | Georgian (ქართული) | Mkhedruli (own alphabet) | Unique script; no Unicode overlap with others |
| Coptic | Coptic (ⲕⲟⲡⲧⲓⲙⲓ) + Arabic (عربي) | Coptic + Arabic | Living language only in liturgy; Arabic is the vernacular |
| Syriac Orthodox | Syriac (ܣܘܪܝܝܐ) + Arabic | Serto script | Aramaic dialect; also Arabic for vernacular |
| Malankara | Malayalam (മലയാളം) | Brahmic script | Official language of Malankara church in Kerala |
| Armenian Apostolic | Armenian (Հայերեն) | Armenian | Unique script; Classical (Grabar) used liturgically |
| Ethiopian Orthodox | Amharic (አማርኛ) + Ge'ez (ግዕዝ) | Ethiopic (Ge'ez script) | Ge'ez = liturgical; Amharic = vernacular |
| Assyrian Church of the East | Assyrian/Neo-Aramaic (ܣܘܪܝܬ) | Madnhaya script | Also Arabic; smallest language community |
| Antiochian | Arabic (عربي) | Arabic | Main liturgical and vernacular language |

### 8.2 Localization Architecture

**Approach: i18n overlay files per tradition**

Rather than duplicating full saint entries, add a translation layer:

```
backend/app/data/
├── oca_julian.json                 # Base: English
├── goarch_hagiographies.json       # Hagiographies: English
├── i18n/
│   ├── el/                         # Greek
│   │   ├── saints_el.json          # Saint names in Greek
│   │   ├── feasts_el.json          # Feast names, troparia, kontakia
│   │   └── hagiographies_el.json   # Full hagiographies in Greek
│   ├── ru/                         # Russian
│   │   ├── saints_ru.json
│   │   ├── feasts_ru.json
│   │   └── hagiographies_ru.json
│   ├── sr/                         # Serbian (Cyrillic)
│   ├── ro/                         # Romanian
│   ├── bg/                         # Bulgarian
│   ├── ka/                         # Georgian
│   ├── ar/                         # Arabic (Coptic, Syriac, Antiochian)
│   ├── hy/                         # Armenian
│   ├── am/                         # Amharic (Ethiopian)
│   ├── ml/                         # Malayalam (Malankara)
│   └── syc/                        # Syriac (Classical Aramaic; ISO 639-3: syc)
```

**Translation key structure:**

```json
// i18n/ru/saints_ru.json
{
  "saint_keys": {
    "Seraphim of Sarov": {
      "name": "Серафим Саровский",
      "title": "Преподобный Серафим Саровский, Чудотворец",
      "feast_type": "Преподобный"
    }
  }
}
```

Key matches English name → translated output. Avoids duplicating date/feast structure.

### 8.3 API Changes for i18n

**New query param:** `?lang=el` (ISO 639-1/639-3 code)

```
GET /api/v1/saints?date=2024-01-07&tradition=russian&lang=ru
```

**Response merging logic:**
1. Load base saint record (English)
2. If `lang` param supplied and `i18n/{lang}/saints_{lang}.json` exists:
   - Overlay translated `name`, `title`, `feast_type`
   - Overlay translated `notes` (hagiography excerpt) if available
3. Return merged record; fall back to English for any missing fields

**`Accept-Language` header support:** Also accept standard HTTP `Accept-Language` header as fallback.

### 8.4 Localization Data Sources Per Language

| Language | Source for Saint Names/Hagiographies |
|---|---|
| **Greek** | `patriarchate.org` (Ecumenical Patriarchate) — official Greek texts; `goarch.org` Greek-language versions |
| **Russian** | `days.pravoslavie.ru` — comprehensive Russian hagiographies; `azbyka.ru` — Orthodox encyclopedia in Russian |
| **Serbian** | `svetosavlje.org` — Serbian hagiographies; `spc.rs` calendar |
| **Romanian** | `patriarhia.ro` — official Romanian texts |
| **Bulgarian** | `bg-patriarshia.bg` — official Bulgarian |
| **Georgian** | `patriarchate.ge` — official Georgian; limited English-language secondary source for cross-referencing |
| **Arabic** | `st-takla.org` — already has Arabic Coptic Synaxarium; `copticsyriachurch.org` |
| **Armenian** | `armenianchurch.org/hy/` — official Armenian-language site |
| **Amharic** | `eotcmk.org` — Ethiopian Orthodox Church; Amharic Wikipedia as cross-reference |
| **Malayalam** | `malankaraorthodoxchurch.in` — Malankara church site has Malayalam content |
| **Syriac** | `syriacorthodoxresources.org` — has Syriac text resources |

### 8.5 Frontend i18n

- Use `react-i18next` or `i18next` for UI string translations
- Language selector UI: per-tradition language auto-selection + manual override
- RTL support needed for: Arabic (ar), Syriac (syc) — requires `dir="rtl"` in HTML + CSS mirroring
- Font support: ensure NB-Byzantine or fallback covers all scripts (Greek, Cyrillic, Georgian alphabet each need specific Unicode ranges)
- Font fallback stack per locale:
  - Georgian: `Sylfaen`, `BPG Arial`, system-ui
  - Arabic/Syriac: `Noto Naskh Arabic`, `Scheherazade New`
  - Ethiopic: `Noto Sans Ethiopic`, `Ethiopia Jiret`
  - Armenian: `Noto Serif Armenian`, `GHEA Grapalat`
  - Malayalam: `Noto Serif Malayalam`, `Rachana`

### 8.6 Church Slavonic (Liturgical Language)

Church Slavonic (`cu`, ISO 639-2) is the liturgical language for Russian, Serbian, Bulgarian, and some Romanian Orthodox churches. It is not a vernacular but is used in actual liturgical texts (troparia, kontakia, stichera).

- Unicode support: Church Slavonic uses Cyrillic extended + special combining characters (`U+2DE0–U+2DFF`, `U+A640–U+A69F`)
- Source: `ponomar.net` — the Ponomar Project provides digitized Church Slavonic liturgical texts under CC-BY-SA
- The `Ponomar Unicode` font supports full Church Slavonic rendering
- This would be optional/advanced feature — show original Slavonic alongside Russian/Serbian translations

### 8.7 Implementation Prerequisites Before Localization

Before any i18n work begins, these must be stable:
1. All English saint data complete and validated for all 16 traditions
2. `saint_key` normalization strategy finalized (canonical English name as cross-language key)
3. Backend API versioning in place (i18n is a breaking change to response shape)
4. Font bundling strategy for non-Latin scripts
5. RTL layout testing infrastructure

---

## Verification Plan

1. Run each import script against its source; verify output JSON validates against `CalendarEntry` schema
2. Spot-check 10 random saints per tradition: correct name, feast type, date mapping
3. Start backend with new data; hit `/api/v1/saints?date=YYYY-MM-DD&tradition=coptic` etc.
4. Verify no regressions in existing Byzantine data (base `oca_julian.json` unchanged)
5. Check `canonization_scope` tags are correctly set (`local` vs `oriental` vs `pan-orthodox`)
6. For GOARCH: verify hagiography text appears in `/api/v1/hagiography` endpoint


---

## Sources for the non-chalcedonian Churches

Ethiopian church calendar: 
Google: EOTC Saint Days
Created by: blainhaile@gmail.com
https://www.ethiopianorthodox.org/english/calendar.html
https://en.wikipedia.org/wiki/Calendar_of_saints_(Orthodox_Tewahedo)
https://en.wikipedia.org/wiki/Ethiopian_calendar#Anno_Mundi
https://en.wikipedia.org/wiki/Ethiopian_Orthodox_Tewahedo_Church
https://www.ethiopiancalendar.net/ethiopian-orthodox-fasting-calendar
https://sites.google.com/view/eotcpathway/home/saint-days
https://en.wikipedia.org/wiki/Calendar_of_saints_(Orthodox_Tewahedo)
https://www.ethiopianorthodox.org/english/calendar.html
https://sites.google.com/view/eotcpathway/home/saint-days


Armenian Apostolic Church:
https://armenianchurchsydney.org.au/event/commemoration-of-the-holy-forefathers-2/
https://www.armenianchurch.org/en/Liturgical-Calendar/
https://armenianchurch.ge/en/kalendar-prazdnikov
https://en.wikipedia.org/wiki/Calendar_of_saints_(Armenian_Apostolic_Church)
https://shnorhali.com/calendar/
https://www.saintsarkis.org/Calendar/Feast-Saints
https://www.armenianchurch.org/en/Liturgical-Calendar/
https://www.stjohnarmenianchurch.org/saints-and-feasts/
https://armenianchurchsydney.org.au/learning/feasts-saints/
https://armenianchurchsydney.org.au/saints-days/
https://www.armenianorthodoxtheology.com/armenianchurchcalendar
https://60550fcc-0422-43b5-a860-37640a5791e8.filesusr.com/ugd/f4ddb8_68c75a00a50d44e1a630bbbc55cc42e8.ics?dn=2026_calendar_EN.ics


Malankara Orthodox:
https://talmido.org/index.php?title=Liturgical_Calendar
https://sgoci.com/calendar.php?month=6&year=2026
www.neamericandiocese.org/menu/main-menu/liturgical-calendar/99
https://calendar.mosc.in/
https://mosc.in/downloads/
https://www.malankara.com/lectionary
https://mosc.in/uploads/2023/12/Panjangom_English_25_Online.pdf
https://mosc-temp.com/mosc-redesign/the-church/church-calendar

For the Constantinople Pogrom of 1955 you did not add supporting images (that exist). Also - for the Cyprus occupation - you need to add timeline event (biased in favor of the Greeks) about the attack in the operation atilla.


Assyrian:
https://news.assyrianchurch.org/liturgical-calendar/
https://en.wikipedia.org/wiki/Assyrian_calendar
https://acoecalifornia.org/calendar.html
https://calendar.assyrianchurch.org/english-liturgical-calendar/
