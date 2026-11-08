from pathlib import Path

from change_impact.index import build_index


def test_index_records_aliases_scopes_and_lines(tmp_path: Path) -> None:
    (tmp_path / "helpers.py").write_text("def check(value):\n    return value > 0\n")
    (tmp_path / "api.py").write_text(
        "from helpers import check as validate\n\n"
        "class Service:\n"
        "    def run(self, value):\n"
        "        return validate(value)\n"
    )
    index = build_index(tmp_path)
    assert index["api"].imports["validate"] == "helpers.check"
    assert [(s.qualname, s.line) for s in index["api"].symbols] == [("Service", 3), ("Service.run", 4)]
    assert [(c.caller, c.expression, c.line) for c in index["api"].calls] == [("Service.run", "validate", 5)]
