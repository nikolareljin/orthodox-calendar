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
