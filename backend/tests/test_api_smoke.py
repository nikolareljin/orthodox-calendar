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
