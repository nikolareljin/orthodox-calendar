"""Regression test for the CDX timestamp search paths.

The repo-local tmp/ path was computed and then omitted from the search list, so
that location was never actually read.
"""

from pathlib import Path

import enrich_goarch_from_wayback as ew

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_repo_local_tmp_is_searched():
    assert _REPO_ROOT / "tmp" / "cdx_timestamps.json" in ew._cdx_search_paths()


def test_committed_snapshot_is_searched():
    assert _REPO_ROOT / "scripts" / "goarch_cdx_timestamps.json" in ew._cdx_search_paths()


def test_no_path_escapes_the_repository():
    # The old expression resolved one level above the repo root.
    for path in ew._cdx_search_paths():
        assert path == Path("/tmp/cdx_timestamps.json") or _REPO_ROOT in path.parents


def test_scratch_overrides_precede_the_committed_snapshot():
    paths = ew._cdx_search_paths()
    assert paths.index(_REPO_ROOT / "tmp" / "cdx_timestamps.json") < paths.index(
        _REPO_ROOT / "scripts" / "goarch_cdx_timestamps.json"
    )


def test_st_abbreviation_is_stripped():
    # \bst\.\b could never match: "." and the space after it are both non-word
    # characters, so there is no boundary between them. "St. Basil" keyed as
    # "stbasil" while "Saint Basil" keyed as "basil", and the two never matched.
    assert ew._normalize("St. Basil") == ew._normalize("Saint Basil")


def test_bare_st_is_also_stripped():
    assert ew._normalize("St Basil") == ew._normalize("Basil")


def test_names_beginning_with_st_are_untouched():
    # \bst\b must not eat the start of "Stephen" or "Stylianos".
    assert ew._normalize("Stephen") == "stephen"
    assert ew._normalize("Stylianos the Wonderworker").startswith("stylianos")


def test_saint_key_uses_title_when_present():
    assert ew._saint_key("Basil", "St. Basil the Great") == ew._normalize("St. Basil the Great")


def test_normalization_discards_punctuation_and_case():
    assert ew._normalize("St. Basil, the Great") == ew._normalize("saint basil the great")
