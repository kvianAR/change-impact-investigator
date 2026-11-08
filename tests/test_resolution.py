from pathlib import Path

from change_impact.index import build_index
from change_impact.trace import trace_callers


def test_parameter_shadowing_and_function_local_import(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(): pass\n")
    (tmp_path / "a.py").write_text(
        "from v import check\n"
        "def shadow(check):\n    check()\n"
        "def local():\n    from v import check as valid\n    valid()\n"
        "def other():\n    valid()\n"
    )
    result = trace_callers(build_index(tmp_path), "v:check")
    assert [path[0]["caller"] for path in result["paths"]] == ["a:local"]
    assert {call["expression"] for call in result["unresolved_dynamic_calls"]} == {"check", "valid"}


def test_method_calls_and_dotted_module_imports(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "v.py").write_text("def check(): pass\n")
    (tmp_path / "a.py").write_text(
        "import package.v\n"
        "class Service:\n"
        "    def validate(self):\n        package.v.check()\n"
        "    def run(self):\n        self.validate()\n"
    )
    result = trace_callers(build_index(tmp_path), "package.v:check")
    assert [path[0]["caller"] for path in result["paths"]] == [
        "a:Service.validate",
        "a:Service.run",
    ]
    assert result["paths"][0][0]["target_file"] == "package/v.py"


def test_package_reexport(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "__init__.py").write_text("from .v import check\n")
    (package / "v.py").write_text("def check(): pass\n")
    (tmp_path / "a.py").write_text("from package import check\ndef run():\n    check()\n")
    assert (
        trace_callers(build_index(tmp_path), "package.v:check")["paths"][0][0]["caller"] == "a:run"
    )


def test_lambda_calls_are_separate_from_enclosing_function(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def check(): pass\ndef make_callback():\n    return lambda: check()\n"
    )
    paths = trace_callers(build_index(tmp_path), "a:check")["paths"]
    assert len(paths) == 1
    assert "<lambda>" in paths[0][0]["caller"]


def test_comprehension_target_does_not_shadow_enclosing_function(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def check(): pass\ndef run(items):\n    [check() for check in items]\n    check()\n"
    )
    result = trace_callers(build_index(tmp_path), "a:check")
    assert len(result["paths"]) == 1
    assert result["paths"][0][0]["line"] == 4


def test_constructor_inference_has_explicit_resolution_label(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class Service:\n    def check(self): pass\ndef run():\n    service = Service()\n    service.check()\n"
    )
    result = trace_callers(build_index(tmp_path), "a:Service.check")
    assert result["paths"][0][0]["resolution"] == "constructor_inference"


def test_default_expression_is_evaluated_in_enclosing_scope(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\ndef run(value=check()):\n    pass\n")
    paths = trace_callers(build_index(tmp_path), "a:check")["paths"]
    assert paths[0][0]["caller"] == "a:<module>"


def test_parameter_rebound_by_import_remains_unresolved(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(): pass\n")
    (tmp_path / "a.py").write_text(
        "def run(check):\n    check()\n    from v import check\n    check()\n"
    )
    assert trace_callers(build_index(tmp_path), "v:check")["paths"] == []


def test_builtin_named_callback_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\ndef run(len):\n    len()\n")
    unresolved = trace_callers(build_index(tmp_path), "a:check")["unresolved_dynamic_calls"]
    assert unresolved[0]["expression"] == "len"
