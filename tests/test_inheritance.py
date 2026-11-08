from pathlib import Path

from change_impact.index import build_index
from change_impact.trace import trace_callers


def test_c3_diamond_uses_python_method_order(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class Base:\n    def check(self): pass\nclass Left(Base): pass\nclass Right(Base):\n    def check(self): pass\nclass Child(Left, Right):\n    def run(self): self.check()\n"
    )
    index = build_index(tmp_path)
    assert trace_callers(index, "a:Right.check")["paths"][0][0]["caller"] == "a:Child.run"
    assert trace_callers(index, "a:Base.check")["paths"] == []


def test_super_and_annotated_parameter_calls(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class Base:\n    def check(self): pass\nclass Child(Base):\n    def check(self): super().check()\ndef run(service: Child):\n    service.check()\n"
    )
    result = trace_callers(build_index(tmp_path), "a:Base.check")
    assert result["paths"][0][0]["resolution"] == "super_static"
    assert result["paths"][1][0]["resolution"] == "annotation_inference"


def test_unknown_external_base_keeps_inherited_call_unresolved(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from external import Unknown\nclass Base:\n    def check(self): pass\nclass Child(Unknown, Base):\n    def run(self): self.check()\n"
    )
    result = trace_callers(build_index(tmp_path), "a:Base.check")
    assert result["paths"] == []
    assert result["unresolved_dynamic_calls"][0]["expression"] == "self.check"


def test_constructor_assignment_overrides_parameter_annotation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class A:\n    def check(self): pass\nclass B:\n    def check(self): pass\ndef run(value: A):\n    value = B()\n    value.check()\n"
    )
    index = build_index(tmp_path)
    assert trace_callers(index, "a:A.check")["paths"] == []
    assert trace_callers(index, "a:B.check")["paths"][0][0]["resolution"] == "constructor_inference"


def test_runtime_method_replacement_is_unresolved(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class A:\n    def check(self): pass\n    def run(self, callback):\n        self.check = callback\n        self.check()\n"
    )
    result = trace_callers(build_index(tmp_path), "a:A.check")
    assert result["paths"] == []
    assert result["unresolved_dynamic_calls"][0]["expression"] == "self.check"
