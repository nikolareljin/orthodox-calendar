import urllib.error
from io import BytesIO

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


def test_revised_julian_readings_use_revised_calendar_date_after_divergence(monkeypatch) -> None:
    requested_urls = []

    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_urlopen(url, *args, **kwargs):
        requested_urls.append(url)
        return FakeResponse(b'{"readings": []}')

    monkeypatch.setattr(main._urllib_request, "urlopen", fake_urlopen)

    response = client.get("/api/v1/readings?day=2800-03-01&tradition=greek")

    assert response.status_code == 200
    assert requested_urls == ["https://orthocal.info/api/gregorian/2800/3/2/"]


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


def test_pascha_shown_on_correct_gregorian_date_not_today() -> None:
    """Regression: Pascha must appear on its computed Gregorian date for Julian traditions.

    In 2026 Pascha = April 12. The old OCA dataset stored Pascha at month_day
    "05-05" (2024 Gregorian scrape date). For Julian traditions this matched
    Gregorian May 18 (Julian May 5 → key "05-05"), showing Pascha on the wrong day.
    """
    # Pascha must appear on April 12 for both Julian and Revised-Julian traditions
    for tradition in ("serbian", "georgian", "greek"):
        resp = client.get(f"/api/v1/saints?day=2026-04-12&traditions={tradition}")
        assert resp.status_code == 200
        saints = resp.json()
        assert saints, f"{tradition}: no saints on Pascha 2026"
        titles = [s["title"] for entry in saints for s in entry["saints"]]
        assert any("HOLY PASCHA" in (t or "") for t in titles), (
            f"{tradition}: Pascha missing on 2026-04-12; got {titles[:5]}"
        )

    # Pascha must NOT appear on May 18 (Julian May 5 — old wrong match)
    for tradition in ("serbian", "georgian"):
        resp = client.get(f"/api/v1/saints?day=2026-05-18&traditions={tradition}")
        assert resp.status_code == 200
        saints = resp.json()
        titles = [s["title"] for entry in saints for s in entry["saints"]]
        assert not any("HOLY PASCHA" in (t or "") for t in titles), (
            f"{tradition}: Pascha wrongly shown on 2026-05-18; got {titles[:5]}"
        )


def test_moon_phase_returns_expected_shape() -> None:
    response = client.get("/api/v1/moon-phase?day=2026-05-13")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"date", "phase", "phase_name", "emoji", "illumination"}
    assert payload["date"] == "2026-05-13"
    assert 0 <= payload["phase"] <= 1
    assert 0 <= payload["illumination"] <= 1
    assert payload["phase_name"]
