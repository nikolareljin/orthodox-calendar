import urllib.error

from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readings_upstream_failure_returns_502(monkeypatch) -> None:
    def fail_urlopen(*args, **kwargs):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr(main._urllib_request, "urlopen", fail_urlopen)

    response = client.get("/api/v1/readings?day=2026-05-13&tradition=greek")

    assert response.status_code == 502
    assert response.json()["detail"] == "Readings upstream is unavailable"


def test_month_calendar_returns_date_keyed_summary() -> None:
    response = client.get("/api/v1/calendar?year=2026&month=1&tradition=serbian")

    assert response.status_code == 200
    payload = response.json()
    assert "2026-01-07" in payload
    assert set(payload["2026-01-07"]) == {"feast_types", "main_feast", "calendar_date"}
    assert isinstance(payload["2026-01-07"]["feast_types"], list)
    assert payload["2026-01-07"]["main_feast"]


def test_movable_feasts_includes_pascha_for_known_year() -> None:
    response = client.get("/api/v1/movable-feasts?year=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["pascha_gregorian"] == "2026-04-12"
    assert payload["feasts"]["pascha"] == "2026-04-12"


def test_moon_phase_returns_expected_shape() -> None:
    response = client.get("/api/v1/moon-phase?day=2026-05-13")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"date", "phase", "phase_name", "emoji", "illumination"}
    assert payload["date"] == "2026-05-13"
    assert 0 <= payload["phase"] <= 1
    assert 0 <= payload["illumination"] <= 1
    assert payload["phase_name"]
