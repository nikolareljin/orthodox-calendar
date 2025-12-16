# Backend (FastAPI)

## Run & develop
```bash
cd orthodox-calendar/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Env vars:
- `ORTHODOX_CALENDAR_DATA_PATH`: optional directory/file with JSON entries matching `app/data/saints_sample.json`; multiple files merge.

## Docker
- From repo root: `./start` (add `-b` to rebuild) starts backend+frontend via Docker Compose; backend exposed on `:8000`.

## API
- `GET /api/v1/saints?day=YYYY-MM-DD&traditions=serbian&traditions=greek`
  - Returns saints/feasts for the civil date; converts to Julian when needed.
- `POST /api/v1/name-days`
  - Body: `{"date": "YYYY-MM-DD", "traditions": ["serbian"], "contacts": [{"full_name": "Andrew Example"}]}`
  - Returns contacts whose first name matches a saint/feast of the day.
- `GET /api/v1/saints.ics?tradition=serbian&start=YYYY-MM-DD&days=365`
  - Generates an iCal feed of all-day events for the tradition.

See `backend/app/models.py` for response schemas.

## Data model
- `month_day` is stored on the tradition’s calendar (`julian` or `revised`).
- `saints` entries include name/title/feast_type/hagiography_url/icon_url/notes.

## Testing
- Linting/formatting not yet configured; run syntax check: `python3 -m py_compile $(find app -name '*.py')`.
- Add `pytest` for unit tests (e.g., calendar conversion, data loading, ICS generation).

## Connectors
- Stubs in `backend/app/connectors/` for Google, Outlook, Yahoo, Facebook, and a local `DemoConnector` (reads JSON contacts).
  - Implement `list_contacts()` and `schedule_name_day(match)` with real APIs or messaging.

## ICS feeds
- Generated dynamically in `app/services/ical.py`; uses current calendar index and selected tradition/date range.
