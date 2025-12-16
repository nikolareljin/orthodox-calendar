# orthodox-calendar frontend

React single-page UI for the `orthodox-calendar` API.

## Quickstart
```bash
cd orthodox-calendar/frontend
npm install
npm run dev
```
Set `VITE_API_BASE` in a `.env` file if your API is not at `http://localhost:8000`.

## Docker
- From the repo root, `./start` launches backend + frontend via Docker Compose (frontend served on port 4173). `./stop` tears down.

## Features
- Pick a date and multiple traditions; view saints/feasts of the day with hagiography links.
- Generate ICS subscription links per tradition (start date + span).
- Paste JSON contacts and check who has a name-day today.

## Notes
- Traditions list is defined in `src/traditions.js` and should match the backend config.
- API helpers live in `src/api.js`.
```
