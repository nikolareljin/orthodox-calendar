"""Provenance rules for overlay hagiography text.

_format_hagiography_response reports source="goarch" for any extended_notes with
no recorded source. Promoting an untagged overlay's notes into extended_notes
therefore both shadowed the base OCA hagiography and mislabeled it, so the
promotion is gated on the overlay carrying a provenance tag.
"""

from app import data_loader
from app.models import CalendarEntry, Saint
from app.services.saints import _apply_overlay, _format_hagiography_response


def _base_with_oca_notes() -> Saint:
    return Saint(
        name="Basil the Great",
        notes="OCA life of Basil.",
        hagiography_url="https://www.oca.org/saints/lives/0000/01/01/1-basil",
    )


def test_plain_tradition_overlay_does_not_promote_notes() -> None:
    base = _base_with_oca_notes()
    overlay = Saint(name="Basil the Great", notes="Serbian tradition remark.")

    _apply_overlay(base, overlay)

    assert base.extended_notes is None
    assert base.extended_notes_source is None


def test_plain_tradition_overlay_leaves_hagiography_reported_as_oca() -> None:
    base = _base_with_oca_notes()
    _apply_overlay(base, Saint(name="Basil the Great", notes="Serbian tradition remark."))

    response = _format_hagiography_response(base)

    assert response.source == "oca"
    assert response.hagiography == "OCA life of Basil."


def test_provenance_tagged_overlay_promotes_notes() -> None:
    base = _base_with_oca_notes()
    overlay = Saint(
        name="Basil the Great",
        notes="Curated neobyzantine life.",
        extended_notes_source="neobyzantine",
    )

    _apply_overlay(base, overlay)

    assert base.extended_notes == "Curated neobyzantine life."
    assert base.extended_notes_source == "neobyzantine"


def test_promoted_notes_are_reported_as_neobyzantine() -> None:
    base = _base_with_oca_notes()
    _apply_overlay(
        base,
        Saint(
            name="Basil the Great",
            notes="Curated neobyzantine life.",
            extended_notes_source="neobyzantine",
        ),
    )

    response = _format_hagiography_response(base)

    assert response.source == "neobyzantine"
    assert response.hagiography == "Curated neobyzantine life."


def test_cross_link_metadata_alone_also_permits_promotion() -> None:
    """An entry carrying a neobyzantine link is neobyzantine even if untagged."""
    base = _base_with_oca_notes()
    overlay = Saint(
        name="Basil the Great",
        notes="Curated neobyzantine life.",
        neobyzantine_url="https://neobyzantine.org/actors/basil-the-great",
    )

    _apply_overlay(base, overlay)

    assert base.extended_notes == "Curated neobyzantine life."
    assert base.extended_notes_source == "neobyzantine"


def test_untagged_extended_notes_keep_the_goarch_default() -> None:
    """GOARCH-enriched overlays carry extended_notes directly and stay source=goarch."""
    base = Saint(name="Basil the Great")
    _apply_overlay(base, Saint(name="Basil the Great", extended_notes="GOARCH chapel text."))

    assert base.extended_notes == "GOARCH chapel text."
    assert base.extended_notes_source is None
    assert _format_hagiography_response(base).source == "goarch"


def test_loader_stamps_provenance_on_the_curated_dataset() -> None:
    entry = CalendarEntry(
        month_day="01-01",
        tradition="oca",
        calendar="julian",
        saints=[Saint(name="Basil the Great", notes="Curated neobyzantine life.")],
    )

    data_loader._stamp_provenance(entry, "neobyzantine")

    assert entry.saints[0].extended_notes_source == "neobyzantine"


def test_loader_does_not_overwrite_a_declared_provenance() -> None:
    entry = CalendarEntry(
        month_day="01-01",
        tradition="oca",
        calendar="julian",
        saints=[
            Saint(name="Basil the Great", notes="text", extended_notes_source="goarch"),
        ],
    )

    data_loader._stamp_provenance(entry, "neobyzantine")

    assert entry.saints[0].extended_notes_source == "goarch"


def test_loader_leaves_textless_saints_untagged() -> None:
    entry = CalendarEntry(
        month_day="01-01",
        tradition="oca",
        calendar="julian",
        saints=[Saint(name="Basil the Great")],
    )

    data_loader._stamp_provenance(entry, "neobyzantine")

    assert entry.saints[0].extended_notes_source is None


def test_curated_dataset_is_registered_for_stamping() -> None:
    assert "neobyzantine_hagiographies.json" in data_loader.DEFAULT_DATA_FILES
    assert data_loader._DATASET_PROVENANCE["neobyzantine_hagiographies.json"] == "neobyzantine"


def test_stamped_notes_are_attributed_even_without_promotion() -> None:
    """A curated entry that never overlays anything is still attributable.

    It reported "notes" when it stood alone and "neobyzantine" when it merged
    onto an OCA saint -- the same text, two different sources.
    """
    saint = Saint(
        name="Circumcision of Our Lord",
        notes="Curated neobyzantine life.",
        extended_notes_source="neobyzantine",
    )

    assert _format_hagiography_response(saint).source == "neobyzantine"


def test_unstamped_notes_without_an_oca_url_are_still_plain_notes() -> None:
    saint = Saint(name="Some Saint", notes="A remark.")

    assert _format_hagiography_response(saint).source == "notes"


def test_oca_url_still_wins_for_unstamped_notes() -> None:
    saint = Saint(
        name="Some Saint",
        notes="A life.",
        hagiography_url="https://www.oca.org/saints/lives/0000/01/01/1-some",
    )

    assert _format_hagiography_response(saint).source == "oca"
