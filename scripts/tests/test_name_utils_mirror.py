"""_name_utils must stay in step with the backend it claims to mirror.

These scripts write the data the backend reads, so a normalizer that disagrees
produces keys the service will never match. It has drifted once already:
"great" was removed from saints._DROP_TOKENS to stop "Basil the Great"
collapsing to "basil", and the mirror kept dropping it.

The backend source is parsed rather than imported: scripts-scan installs only
pytest, so fastapi and pydantic are not available to this suite.
"""

import ast
from pathlib import Path

import _name_utils as nu

_BACKEND_SAINTS = Path(__file__).resolve().parents[2] / "backend" / "app" / "services" / "saints.py"


def _backend_module() -> ast.Module:
    return ast.parse(_BACKEND_SAINTS.read_text())


def _assigned_value(name: str) -> ast.expr:
    for node in _backend_module().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise AssertionError(f"{name} not found in {_BACKEND_SAINTS}")


def _backend_drop_tokens() -> set[str]:
    return set(ast.literal_eval(_assigned_value("_DROP_TOKENS")))


def _backend_pattern(name: str) -> str:
    """Recover the pattern string from a `_re.compile(r"...", flags)` call."""
    call = _assigned_value(name)
    assert isinstance(call, ast.Call), f"{name} is not a compile() call"
    return ast.literal_eval(call.args[0])


def test_backend_source_is_where_we_think_it_is():
    assert _BACKEND_SAINTS.is_file(), _BACKEND_SAINTS


def test_drop_tokens_match_the_backend():
    assert nu._DROP_TOKENS == _backend_drop_tokens()


def test_great_is_dropped_by_neither():
    # The specific drift this guard was written for.
    assert "great" not in nu._DROP_TOKENS
    assert "great" not in _backend_drop_tokens()


def test_honorific_pattern_matches_the_backend():
    assert nu._HONORIFIC_RE.pattern == _backend_pattern("_HONORIFIC_RE")


def test_event_prefix_pattern_matches_the_backend():
    assert nu._EVENT_PREFIX_RE.pattern == _backend_pattern("_EVENT_PREFIX_RE")


def test_the_epithet_survives_normalization():
    assert "great" in nu.normalize("Basil the Great").split()
    assert "saint" not in nu.normalize("Saint Basil the Great").split()
