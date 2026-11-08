import subprocess
from pathlib import Path

import pytest

from change_impact.impact import inspect_change_impact


def commit_all(root: Path) -> None:
    for arguments in [
        ["init"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
        ["add", "."],
        ["commit", "-m", "baseline"],
    ]:
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_deleted_validator_preserves_base_endpoint_evidence(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(value):\n    return bool(value)\n")
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\nfrom v import check\napp = FastAPI()\n@app.post('/orders')\ndef route(value):\n    return check(value)\n"
    )
    commit_all(tmp_path)
    (tmp_path / "v.py").unlink()
    impact = inspect_change_impact(tmp_path)["impacts"][0]
    assert impact["reason"] == "removed_symbol"
    assert impact["evidence_state"] == "base"
    assert impact["affected_routes"][0]["path"] == "/orders"


def test_import_only_change_marks_module_functions(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from old import check\ndef run(value):\n    return check(value)\n"
    )
    commit_all(tmp_path)
    (tmp_path / "a.py").write_text(
        "from new import check\ndef run(value):\n    return check(value)\n"
    )
    result = inspect_change_impact(tmp_path)
    assert result["impacts"][0]["reason"] == "module_level_change"
    assert result["module_level_changes"][0]["lines"] == [1]


def test_quoted_filename_and_subdirectory_input(tmp_path: Path) -> None:
    filename = 'odd "name.py'
    (tmp_path / filename).write_text("def check():\n    return 1\n")
    commit_all(tmp_path)
    (tmp_path / filename).write_text("def check():\n    return 2\n")
    child = tmp_path / "child"
    child.mkdir()
    result = inspect_change_impact(child)
    assert result["repository"] == str(tmp_path.resolve())
    assert result["impacts"][0]["symbol"]["file"] == filename


def test_deleted_body_line_maps_to_existing_function(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check():\n    value = 1\n    return value\n")
    commit_all(tmp_path)
    (tmp_path / "a.py").write_text("def check():\n    return value\n")
    result = inspect_change_impact(tmp_path)
    assert result["impacts"][0]["symbol"]["qualname"] == "check"
    assert result["impacts"][0]["evidence_state"] == "working_tree"


def test_invalid_base_is_clear_error(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\n")
    commit_all(tmp_path)
    with pytest.raises(ValueError, match="base revision"):
        inspect_change_impact(tmp_path, base="does-not-exist")


def test_unparseable_change_keeps_historical_evidence(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\n")
    commit_all(tmp_path)
    (tmp_path / "a.py").write_text("def check(\n")
    result = inspect_change_impact(tmp_path)
    assert result["impacts"][0]["reason"] == "current_source_unparseable"
    assert result["diagnostics"][0]["reason"] == "SyntaxError"


def test_comment_only_diff_has_no_code_impact(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("def check():\n    return 1\n")
    commit_all(tmp_path)
    path.write_text("# explanation\n\ndef check():\n    return 1  # unchanged\n")
    result = inspect_change_impact(tmp_path)
    assert result["changed_files"] == ["a.py"]
    assert result["non_semantic_changed_files"] == ["a.py"]
    assert result["impacts"] == []


def test_body_edit_with_comment_does_not_affect_unchanged_neighbor(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("def changed():\n    return 1\n\ndef neighbor():\n    return 2\n")
    commit_all(tmp_path)
    path.write_text(
        "def changed():\n    return 3\n\n# neighbor docs\ndef neighbor():\n    return 2\n"
    )
    result = inspect_change_impact(tmp_path)
    assert [item["symbol"]["qualname"] for item in result["impacts"]] == ["changed"]
