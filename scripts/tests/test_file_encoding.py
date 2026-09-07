"""Scripts that handle Greek and Cyrillic names must name their encoding.

Path reads and writes default to the platform encoding. Under a POSIX locale
that is ASCII, so writing greek_saints.json with ensure_ascii=False raises
UnicodeEncodeError -- the data these scripts exist to produce is exactly the
data the default cannot encode.

The scan walks the AST rather than the text, so prose and regex literals that
merely mention these calls are not mistaken for them.
"""

import ast
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_TEXT_IO = {"read_text", "write_text"}


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _TEXT_IO:
            if not any(kw.arg == "encoding" for kw in node.keywords):
                found.append(f"{path.name}:{node.lineno} .{func.attr}()")
    return found


def _scan(paths) -> list[str]:
    return [o for path in sorted(paths) for o in _offenders(path)]


def test_every_script_names_its_encoding():
    offenders = _scan(_SCRIPTS.glob("*.py"))
    assert not offenders, "text IO without encoding=: " + "; ".join(offenders)


def test_the_test_suite_names_its_encoding_too():
    offenders = _scan((_SCRIPTS / "tests").glob("*.py"))
    assert not offenders, "text IO without encoding=: " + "; ".join(offenders)


def test_the_check_detects_a_bare_call(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text("Path('x').read_text()\n", encoding="utf-8")
    assert _offenders(sample) == ["sample.py:1 .read_text()"]


def test_the_check_accepts_an_explicit_encoding(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('Path("x").write_text(data, encoding="utf-8")\n', encoding="utf-8")
    assert not _offenders(sample)


def test_the_check_ignores_a_mention_in_prose(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('"""Do not use .read_text() bare."""\n', encoding="utf-8")
    assert not _offenders(sample)
