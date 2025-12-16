# orthodox-calendar

Service for presenting Orthodox and Oriental Orthodox saints/feasts of the day, surfacing hagiography links, and detecting friends' name-days across calendar systems (Julian vs. Revised/New Calendar/Milankovich).

## Call for collaborators, hosting, and support
- This project should remain open-source and community-owned. If you can contribute calendar data (Synaxarion/Octoechos), API integrations (Google/Outlook/Yahoo/Facebook), or movable-feast logic, please open a PR.
- We need volunteers to help maintain and host a public instance (static ICS feeds + API). If you can provide infrastructure or sponsor hosting/CDN/DB credits, reach out or start an issue describing what you can offer.
- Donations are welcome to cover hosting and data curation time. Add a funding link (OpenCollective/Ko-fi/GitHub Sponsors) and document it in this README once available.

## What it does
- Serves saints/feast entries for Greek, Russian, Serbian, Bulgarian, Romanian, Jerusalem, Antioch, Alexandria, Ethiopian, and Oriental Orthodox traditions.
- Handles calendar drift (Julian vs. Revised/New) when mapping civil dates to church dates.
- Exposes an API to check which of your contacts have a name-day today (birthday-style reminders).
- Provides links to hagiography texts (e.g., Octoechos/Synaxarion/GOARCH/OCA pages) and icon references.
- Ships with connector stubs for Google Calendar/People, Outlook/Microsoft Graph, Yahoo, and Facebook so you can plug in real contact/calendar APIs.

## Quickstart
```bash
cd orthodox-calendar/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for the interactive API explorer.

## API
- `GET /api/v1/saints?day=2024-01-07&traditions=serbian&traditions=russian`
  - Returns saints/feasts for the given civil date across the requested traditions (defaults to all).
  - For Julian traditions, the service automatically shifts the date (currently 13 days) before lookup.
- `POST /api/v1/name-days`
  - Body:
    ```json
    {
      "date": "2024-01-07",
      "traditions": ["serbian", "russian"],
      "contacts": [
        {"full_name": "John Petrovic", "source": "google"},
        {"full_name": "Andrew Example", "source": "facebook"}
      ]
    }
    ```
  - Response lists contacts whose first name matches a saint/feast of the day for the selected traditions.
- `GET /api/v1/saints.ics?tradition=serbian&start=2024-01-01&days=365`
  - Returns an iCal feed of all-day events for the requested tradition across the date span (good for Google/Outlook/Yahoo subscriptions).

## Docker
- From repo root run `./start` (add `-b` to rebuild) to bring up backend+frontend via Docker Compose; `./stop` tears it down.

## Data model
Sample data lives in `app/data/saints_sample.json` and follows:
```json
{
  "month_day": "12-25",
  "tradition": "serbian",
  "calendar": "julian",
  "saints": [
    {
      "name": "Nativity of Christ",
      "feast_type": "Great Feast",
      "hagiography_url": "https://www.oca.org/saints/lives/2024/12/25",
      "icon_url": "https://example.com/icons/nativity.png",
      "notes": "Christmas according to the Julian calendar."
    }
  ],
  "notes": "Fixed feast on the Julian calendar."
}
```
- `month_day` is expressed on the tradition's calendar (Julian/Revised/Gregorian). Civil dates are converted at request time.
- Extend the file or swap in a full Synaxarion/Octoechos dataset as needed.
- To load a fuller dataset, drop `.json` files next to `saints_sample.json` or point `ORTHODOX_CALENDAR_DATA_PATH` to a directory/file containing the same schema; files are merged.

## Calendar handling
- Calendar metadata lives in `app/config.py` (per-tradition calendar system + aliases).
- Current Julian offset is set to 13 days in `app/calendar_logic.py`; adjust per future leap-year shifts if needed.

## Connectors (stubs)
Connector classes live under `app/connectors/`:
- `GoogleConnector`: wire to Google People + Calendar APIs.
- `OutlookConnector`: use Microsoft Graph for contacts + events.
- `YahooConnector`: hook into Yahoo address book + calendar.
- `FacebookConnector`: pull friends from the Graph API and post/share reminders.
- `DemoConnector`: loads contacts from a local JSON file (set `ORTHODOX_CALENDAR_DEMO_CONTACTS` or place `demo_contacts.json` in the backend directory) for offline testing.

Each class exposes `list_contacts()` and `schedule_name_day(match)` so you can fetch contacts and push reminders/events. Inject credentials (OAuth, app secrets) and persistence as appropriate for your deployment.

## Roadmap ideas
- Add full calendar datasets (Synaxarion/Octoechos) and cache them.
- Support movable feasts tied to Pascha (requires Paschalion calculation).
- Add notification pipelines (email, push, SMS) and throttling rules.
- Multi-language hagiography links and icons per locale.
