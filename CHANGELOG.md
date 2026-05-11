# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
