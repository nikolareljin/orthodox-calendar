# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Full liturgical reading texts** — Epistle and Gospel verses are now displayed inline with superscript verse numbers and paragraph breaks. Each reading is a collapsible card (source label + reference + expand toggle). Text is sourced from the `passage[]` array already embedded in orthocal.info responses — no additional API calls required.
- **Church directory** — "Orthodox Churches" grid in the About section with history, founding date, patron saint, website link, and cross glyph for all 12 supported traditions.
- **Moon phase indicator** — lunar phase emoji, name, and illumination percentage displayed in the day-detail badge row (`GET /api/v1/moon-phase`).
- **Fasting glyph** — GOARCH-style fast type shown per day (no fast ✅, fish 🐟, oil+wine 🍷, strict 🌿).
- **Canonization attribution** — saint cards display which church canonized the saint and the scope (Universal / Pan-Orthodox / Local / Oriental) as coloured pills.
- **All-traditions saints** — OCA Julian Synaxarion (`oca_julian.json`, 366 days, 2970 saints) now loads as the shared base for all Byzantine-rite churches. Tradition-specific overlays in `data/traditions/` extend it with recently canonized local saints.
- **Tradition-specific saint overlays** — `serbian_saints.json` (Justin Popović, WWII hierarchs), `greek_saints.json` (Paisios, Porphyrios, Nektarios…), `russian_saints.json` (Tikhon, Elizabeth Feodorovna, Matrona…), `armenian_saints.json`, `coptic_saints.json`, `ethiopian_saints.json`, `georgian_saints.json`.
- **Movable feasts endpoint** — `GET /api/v1/movable-feasts?year=YYYY` returns all 14 Eastern Orthodox movable feast dates via Julian computus + JDN conversion.
- **`import_orthocal.py` script** — fetches all 366 days from orthocal.info for any calendar/tradition and writes a ready-to-use JSON data file.

### Changed
- **Docker — multi-stage backend build** — deps installed in a builder stage and copied to a clean `python:3.12-slim-bookworm` runtime; no build tools in the final image.
- **Docker — non-root runtime user** — backend container now runs as `appuser` (uid 1001), not root.
- **Docker — configurable worker count** — `WEB_CONCURRENCY` env var (default 2) controls uvicorn workers.
- **Docker — backend not exposed to host** — port 8000 removed from `docker-compose.yml`; traffic flows through nginx internal proxy only.
- **Docker — nginx API proxy** — nginx now proxies `/api/` to `backend:8000` internally; `VITE_API_BASE` defaults to `""` so built JS uses relative URLs.
- **Docker — port standardised to 80** — frontend listens on port 80 (configurable via `PORT` env var). Override at `http://localhost:80`.
- **Docker — logging limits** — both containers use `json-file` driver with 10 MB / 3 files rotation to prevent disk fill.
- **Docker — `node:22-alpine` builder** — updated from `node:20-alpine` (22 is current LTS).
- **Docker — `nginx:1.27-alpine` pinned** — was unpinned `nginx:alpine`.
- **Docker — compose version key removed** — deprecated `version: "3.9"` header dropped.
- **Nginx — security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` added.
- **Nginx — `server_tokens off`** — nginx version no longer exposed in response headers.
- **Nginx — compression tuning** — `gzip_comp_level 6`, `gzip_vary on`, `gzip_proxied any`, added `font/woff2` MIME type.
- **Nginx — font cache** — `/fonts/` served with 1-year immutable cache, same as `/assets/`.
- **Nginx — health-check endpoint** — `GET /health-check` returns 200 for load-balancer / Docker health checks.
- **`data_key` renamed to `"oca"`** — was `"serbian"` in config and data files (semantically incorrect).
- **JDN-based Julian↔Gregorian conversion** — replaced hardcoded 13-day offset with full Julian Day Number algorithm valid for any year from 0 AD onward.
- **.dockerignore expanded** — excludes `.git`, `docs/`, `scripts/`, `deploy/`, `*.md`, `.github/` from build contexts.
- **`.env.example` added** — documents `PORT`, `WEB_CONCURRENCY`, and `VITE_API_BASE` variables.

---

## [0.2.0] - 2026-05-11

### Added
- **Monthly calendar grid** — full month view with prev/next navigation and Today shortcut.
- **Feast-level dots** — each calendar cell shows a coloured dot: gold for Great Feasts, blue for regular commemorations. Hovering shows the main feast name.
- **Day detail panel** — clicking any day loads saints, hagiographies, fasting level, tone of the week, liturgical title, and full Epistle/Gospel readings.
- **Expandable hagiographies** — each saint card expands to show the biography excerpt and a link to the full hagiography.
- **Liturgical readings** — `GET /api/v1/readings` proxies orthocal.info (Julian or Gregorian based on tradition) for Epistle/Gospel readings.
- **Month summary endpoint** — `GET /api/v1/calendar?year=&month=&tradition=` returns feast data for the whole month in one call (all in-memory, sub-millisecond).
- **CORS middleware** — backend now allows browser access from any origin, enabling the Vite dev server and GitHub Pages to call the API directly.
- **Dark and light themes** — dark theme uses neobyzantine-org palette (navy `#0d1220`, gold `#CFB53B`, royal blue `#3366CC`); light theme uses Byzantine crimson on white. Theme toggle is persisted in `localStorage`.
- **Tradition sidebar** — vertical sidebar listing all 10 Orthodox traditions; switching tradition reloads both the month summary and day detail instantly.
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — PR gate: gitleaks secret scan, react-scan, python-scan, and data-safety check.
- **GitHub Actions deploy** (`.github/workflows/deploy.yml`) — push to `main` triggers: secret scan → auto-tag from `release/*` branch merge → build frontend with `VITE_BASE=/orthodox-calendar/` → GitHub Pages deploy.
- **nginx:alpine frontend image** — replaces the previous node+serve runtime (~150 MB → ~10 MB image).
- **Docker improvements** — health checks on both services, `restart: unless-stopped`, `depends_on: condition: service_healthy`, `VITE_API_BASE` as a build arg.
- **`VITE_BASE` support** — Vite config reads `VITE_BASE` env var so the built assets work under a subpath (e.g. `/orthodox-calendar/` on GitHub Pages).

### Data
- Added Serbian/Julian hagiographies extracted from neobyzantine.org (47 day entries, Jan–Feb).
- Added OCA full-year saints dataset: 366 days, 2970 saints (Julian/Serbian tradition).

### Fixed
- `build-essential` removed from backend Dockerfile — it caused apt-get timeouts and is not required for the pure-Python dependency set.
- Frontend Dockerfile switched from `npm install -g serve` (failing) to `nginx:alpine`.

---

## [0.1.0] - 2026-04-xx

Initial release: FastAPI backend, React frontend, ICS feed, name-day checker, saints-of-the-day API.
