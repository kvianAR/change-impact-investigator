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
    assert [(s.qualname, s.line) for s in index["api"].symbols] == [
        ("Service", 3),
        ("Service.run", 4),
    ]
    assert [(c.caller, c.expression, c.line) for c in index["api"].calls] == [
        ("Service.run", "validate", 5)
    ]


def test_src_layout_and_package_relative_import(tmp_path: Path) -> None:
    package = tmp_path / "src" / "shop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .validators import check\n")
    (package / "validators.py").write_text("def check(): pass\n")
    index = build_index(tmp_path)
    assert "shop" in index and "shop.validators" in index
    assert index["shop"].imports["check"] == "shop.validators.check"


def test_parse_failure_is_reported(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(\n")
    index = build_index(tmp_path)
    assert index.diagnostics == [{"file": "broken.py", "line": 1, "reason": "SyntaxError"}]
