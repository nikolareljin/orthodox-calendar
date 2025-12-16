# Frontend (React)

## Run & develop
```bash
cd orthodox-calendar/frontend
npm install
npm run dev
```
- Set `VITE_API_BASE` in `.env` if backend is not on `http://localhost:8000`.

## Docker
- Included in repo root `./start`/`./stop` scripts (Docker Compose); served on port `4173`.

## Features
- Select date and traditions; view saints/feasts with hagiography links.
- Build ICS subscription link per tradition/date span.
- Paste JSON contacts to check for name-days (posts to backend).

## Code map
- `src/App.jsx` — main UI.
- `src/api.js` — API calls to backend.
- `src/traditions.js` — tradition labels (align with backend config).
- `src/styles.css` — layout and theme.

## Build
```bash
cd orthodox-calendar/frontend
npm run build
```
Artifacts output to `dist/` (served by Docker image).***
