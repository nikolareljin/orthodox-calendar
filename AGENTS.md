# Repository Guidelines

## Project Structure & Module Organization
- `backend/app`: FastAPI app (`main.py`), calendar logic, data loaders, connectors, and ICS/name-day services. Sample data sits in `backend/app/data`.
- `frontend/src`: React SPA (`App.jsx`, `api.js`, `traditions.js`, `styles.css`) for browsing saints and generating ICS links.
- Top-level scripts: `./build` (install + bundle), `./run` (local backend on :8000 + Vite dev on :5173), `./start`/`./stop` (Docker Compose, frontend on :4173). Run `git submodule update --init --recursive` to fetch `script-helpers`.

## Build, Test, and Development Commands
```bash
# Backend (venv recommended)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install
npm run dev    # dev server
npm run build  # production bundle

# Helpers
./update       # sync all git submodules (script-helpers)
./build        # full install + frontend build
./run          # start backend + frontend dev servers with cleanup
./start -b     # docker-compose up (add -b to rebuild images)
```

## Coding Style & Naming Conventions
- Python 3.11 (see backend Dockerfile); follow PEP 8 with 4-space indents and type hints. Use snake_case for modules/functions, PascalCase for Pydantic models/services, and keep FastAPI routers lean.
- JavaScript/React: functional components, camelCase props/state, and colocate helpers in `src`. Keep API helpers in `api.js` and shared constants in `traditions.js`.
- Keep responses and models explicit; prefer small, testable functions in `app/calendar_logic.py` and `app/services`.

## Testing Guidelines
- No automated suite yet; add backend tests with `pytest` under `backend/tests/` (e.g., calendar drift and ICS generation). Aim for deterministic fixtures; avoid network calls.
- For calendar math, test `julian_gregorian_delta` across centuries (e.g., 2099 vs 2100) and `orthodox_pascha(year)` to confirm Pascha/indiction outputs.
- Frontend: rely on `npm run build` as a smoke check; consider adding lightweight component tests (Vitest/RTL) under `frontend/src/__tests__` when introducing UI changes.
- Before PRs, exercise key flows: `GET /api/v1/saints`, `POST /api/v1/name-days`, and generating ICS links from the UI.

## Commit & Pull Request Guidelines
- Use conventional commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`); keep subjects in imperative mood.
- PRs should describe scope, testing performed, and config changes (env vars like `VITE_API_BASE`, `ORTHODOX_CALENDAR_DATA_PATH`, `ORTHODOX_CALENDAR_DEMO_CONTACTS`). Attach screenshots/GIFs for UI work and sample API payloads for backend changes.
- Keep diffs focused; prefer small PRs with clear reviewer notes on risky areas.

## Configuration & Data Safety
- Do not commit secrets or private datasets. Point `ORTHODOX_CALENDAR_DATA_PATH` to local JSON sources when testing; demo contacts come from `ORTHODOX_CALENDAR_DEMO_CONTACTS` or `backend/demo_contacts.json`.
- For deployments, set `VITE_API_BASE` to the public backend URL and secure OAuth credentials for connectors outside the repo.
