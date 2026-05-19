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

    # Pascha must NOT appear on May 18 (Julian May 5 — old wrong match for Julian traditions)
    for tradition in ("serbian", "georgian"):
        resp = client.get(f"/api/v1/saints?day=2026-05-18&traditions={tradition}")
        assert resp.status_code == 200
        saints = resp.json()
        titles = [s["title"] for entry in saints for s in entry["saints"]]
        assert not any("HOLY PASCHA" in (t or "") for t in titles), (
            f"{tradition}: Pascha wrongly shown on 2026-05-18; got {titles[:5]}"
        )

    # Pascha must NOT appear on May 5 for Revised-Julian (Greek) tradition.
    # The OCA dataset key "05-05" = Gregorian May 5, 2024 Pascha.  For Revised-Julian
    # there is no date conversion, so this key is looked up directly — it must be
    # filtered out and NOT re-injected (+23 days from 2026 Pascha is not a feast).
    resp = client.get("/api/v1/saints?day=2026-05-05&traditions=greek")
    assert resp.status_code == 200
    saints = resp.json()
    titles = [s["title"] for entry in saints for s in entry["saints"]]
    assert not any("PASCHA" in (t or "").upper() for t in titles), (
        f"greek: Pascha wrongly shown on 2026-05-05 (2024 static key); got {titles[:5]}"
    )


def test_holy_fathers_first_council_shown_on_correct_date() -> None:
    """Regression: Sunday of Holy Fathers of First Ecumenical Council (Pascha+42) must
    appear on its computed Gregorian date, not on the stale 2024-scraped key date.

    In 2026 Pascha = April 12, so Pascha+42 = May 24.
    The OCA dataset stored this feast at month_day "06-16" (2024 scrape date).
    For Serbian (Julian), key "06-16" matches Gregorian June 29 (Julian June 16).
    For Greek (Revised-Julian), key "06-16" matches Gregorian June 16.
    """
    keyword = "holy fathers of the first ecumenical council"

    for tradition in ("serbian", "greek"):
        resp = client.get(f"/api/v1/saints?day=2026-05-24&traditions={tradition}")
        assert resp.status_code == 200
        saints = resp.json()
        assert saints, f"{tradition}: no saints on 2026-05-24"
        titles = [s["title"] for entry in saints for s in entry["saints"]]
        assert any(keyword in (t or "").lower() for t in titles), (
            f"{tradition}: Holy Fathers feast missing on 2026-05-24; got {titles[:5]}"
        )

    # Must NOT appear on the stale 2024 drift dates
    for tradition, stale_day in [("serbian", "2026-06-29"), ("greek", "2026-06-16")]:
        resp = client.get(f"/api/v1/saints?day={stale_day}&traditions={tradition}")
        assert resp.status_code == 200
        saints = resp.json()
        titles = [s["title"] for entry in saints for s in entry["saints"]]
        assert not any(keyword in (t or "").lower() for t in titles), (
            f"{tradition}: Holy Fathers wrongly shown on {stale_day}; got {titles[:5]}"
        )


def test_oca_urls_use_tradition_calendar_year_not_2024() -> None:
    """OCA hagiography URLs must reflect the tradition's calendar year, not the 2024 scrape year.

    Serbian (Julian) on Gregorian 2026-01-14 = Julian 2026-01-01.
    Every OCA URL for that day's saints should contain /2026/, not /2024/.
    Greek (Revised-Julian) on Gregorian 2026-01-01 = Rev-Julian 2026-01-01.
    """
    for tradition, day, expected_year in [
        ("serbian", "2026-01-14", "2026"),   # Julian Jan 1, 2026
        ("greek",   "2026-01-01", "2026"),   # Revised-Julian Jan 1, 2026
    ]:
        resp = client.get(f"/api/v1/saints?day={day}&traditions={tradition}")
        assert resp.status_code == 200
        saints_data = resp.json()
        assert saints_data, f"{tradition}: no response for {day}"
        for entry in saints_data:
            for s in entry["saints"]:
                url = s.get("hagiography_url") or ""
                if "oca.org" in url:
                    assert "/2024/" not in url, (
                        f"{tradition}: stale 2024 URL: {url}"
                    )
                    assert f"/{expected_year}/" in url, (
                        f"{tradition}: expected year {expected_year} in URL: {url}"
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
