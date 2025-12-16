# Architecture Overview

## Components
- **Backend (FastAPI)**: serves saints/feast data, name-day detection, and ICS feeds; handles calendar conversions (Julian vs. Revised/New).
- **Frontend (React/Vite)**: SPA for selecting traditions, browsing saints, checking contacts, and generating ICS links.
- **Data layer**: JSON datasets (Synaxarion/Octoechos style) loaded via `ORTHODOX_CALENDAR_DATA_PATH`; indexed per tradition.
- **Connectors**: stubs for Google, Outlook, Yahoo, Facebook, plus a demo local connector for contacts.

## Data flow
1. User selects date/traditions in the frontend.
2. Frontend calls backend `GET /api/v1/saints` and `POST /api/v1/name-days`.
3. Backend maps civil date to tradition calendar, loads indexed saints data, and returns entries; name-day checks compare contact first names to saints of the day.
4. ICS feed is generated on-demand per tradition via `GET /api/v1/saints.ics`.

## Calendar handling
- Julian offset currently fixed at 13 days in `backend/app/calendar_logic.py`.
- Traditions and calendar systems live in `backend/app/config.py`.
- Data entries store `month_day` on the tradition’s calendar; lookup converts the requested civil date.

## Future extensions
- Movable feasts tied to Pascha (Paschalion computation).
- Persistent storage/cache for full Synaxarion datasets.
- Auth + per-user contact syncing and scheduling. 
