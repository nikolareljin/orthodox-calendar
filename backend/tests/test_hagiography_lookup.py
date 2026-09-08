"""Name resolution for /hagiography.

The endpoint answered confidently with the wrong saint. Two causes, both here:
keys are normalized to bare words and were matched as raw substrings, so "basil"
matched "cabasilas"; and candidates were ranked on how much text they carried,
so a composite feast out-ranked the saint's own entry.
"""

from fastapi.testclient import TestClient

from app import main
from app.services.saints import _normalize_saint_text


client = TestClient(main.app)


def _lookup(name: str) -> dict:
    response = client.get("/api/v1/hagiography", params={"saint": name})
    assert response.status_code == 200, response.text
    return response.json()


def test_query_does_not_match_a_saint_who_merely_contains_the_token() -> None:
    # "basil" is a substring of both "cabasilas" and "basilisk".
    assert "Cabasilas" not in _lookup("Basil the Great")["saint"]
    assert "Basilisk" not in _lookup("Basil the Great")["saint"]


def test_basil_the_great_resolves_to_basil_the_great() -> None:
    assert "Basil the Great" in _lookup("Basil the Great")["saint"]


def test_composite_feast_does_not_outrank_the_saints_own_entry() -> None:
    # The Synaxis of the Three Hierarchs names Basil, Gregory and John together
    # and carries more text than any of their individual entries.
    for name in ("Basil the Great", "Gregory the Theologian", "John Chrysostom"):
        assert "Synaxis" not in _lookup(name)["saint"]


def test_each_hierarch_resolves_to_himself() -> None:
    assert "Gregory the Theologian" in _lookup("Gregory the Theologian")["saint"]
    assert "John Chrysostom" in _lookup("John Chrysostom")["saint"]


def test_substring_only_queries_still_resolve() -> None:
    """The looser tier is a fallback, not a removal: partial names still work."""
    assert _lookup("Cabasilas")["source"] != "not_found"
    assert _lookup("Chrysostom")["source"] != "not_found"


def test_great_is_kept_as_an_identifying_epithet() -> None:
    # Honorifics are dropped so sources agree; "the Great" identifies a saint.
    assert "great" in _normalize_saint_text("Basil the Great").split()
    assert "saint" not in _normalize_saint_text("Saint Basil the Great").split()


def test_a_saint_without_the_epithet_is_still_reachable() -> None:
    assert _lookup("Basilisk")["saint"] == "Venerable Basilisk the Hesychast of Siberia"


def test_lookup_is_deterministic() -> None:
    assert {_lookup("Basil the Great")["saint"] for _ in range(3)} == {
        _lookup("Basil the Great")["saint"]
    }


def test_honorific_only_query_is_rejected() -> None:
    assert client.get("/api/v1/hagiography", params={"saint": "saint"}).status_code == 422
