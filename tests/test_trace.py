from pathlib import Path

import pytest

from change_impact.index import build_index
from change_impact.trace import trace_callers


def test_traces_import_alias_and_transitive_caller(tmp_path: Path) -> None:
    (tmp_path / "validators.py").write_text("def check(value):\n    return bool(value)\n")
    (tmp_path / "service.py").write_text(
        "from validators import check as valid\ndef save(value):\n    return valid(value)\n"
    )
    (tmp_path / "api.py").write_text(
        "from service import save\ndef route(value):\n    return save(value)\n"
    )
    result = trace_callers(build_index(tmp_path), "validators:check")
    assert len(result["paths"]) == 2
    assert result["paths"][0][0]["file"] == "service.py"
    assert [edge["file"] for edge in result["paths"][1]] == ["api.py", "service.py"]


def test_ambiguous_name_requires_qualified_symbol(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\n")
    (tmp_path / "b.py").write_text("def check(): pass\n")
    with pytest.raises(ValueError, match="Ambiguous"):
        trace_callers(build_index(tmp_path), "check")


def test_dynamic_call_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def check(): pass\ndef run(name):\n    return getattr(object(), name)()\n"
    )
    result = trace_callers(build_index(tmp_path), "check")
    assert result["unresolved_dynamic_calls"][0]["line"] == 3
