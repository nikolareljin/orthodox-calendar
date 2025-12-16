# orthodox-calendar (monorepo)

Open-source Orthodox/Oriental Orthodox saints and name-day service with a FastAPI backend and React frontend.

## Structure
- `backend/` — FastAPI API, data loaders, calendar logic, connectors.
- `frontend/` — React UI for browsing saints, checking name-days, and generating ICS links.

## Quickstart
- Backend:
  ```bash
  cd orthodox-calendar/backend
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app.main:app --reload
  ```
  Open http://127.0.0.1:8000/docs.
- Frontend:
  ```bash
  cd orthodox-calendar/frontend
  npm install
  npm run dev
  ```
  Set `VITE_API_BASE` to point at the backend if not on `http://localhost:8000`.

## Tooling
- `./build` — install dependencies and build backend/frontend on the host (uses script-helpers).
- `./run` — run backend (uvicorn) and frontend dev server locally with auto-cleanup on Ctrl+C.
- `./start [-b]` — start Dockerized stack (add `-b` to rebuild images). `./stop` to tear down.
- Docker Compose exposes backend on `:8000` and frontend on `:4173`.
- Script helpers come from git submodule `script-helpers` (`git@github.com:nikolareljin/script-helpers.git`). Run `git submodule update --init --recursive` if not already present.

## Contribute, host, and support
- We want volunteers to help expand Synaxarion/Octoechos data, movable-feast logic, and connectors (Google/Outlook/Yahoo/Facebook).
- Hosting help is welcome for a public API + ICS feeds. If you can provide infra or credits, open an issue/PR to coordinate.
- Donations are encouraged to fund hosting and data curation; add funding links (OpenCollective/Ko-fi/GitHub Sponsors) once available.

See `backend/README.md` and `frontend/README.md` for deeper details.
