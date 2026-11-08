"""A small, deterministic Python source index."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Symbol:
    module: str
    qualname: str
    file: str
    line: int
    end_line: int
    kind: str

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]

    @property
    def id(self) -> str:
        return f"{self.module}:{self.qualname}"


@dataclass(frozen=True)
class Call:
    module: str
    file: str
    line: int
    caller: str | None
    expression: str
    kind: str


@dataclass
class Module:
    name: str
    file: str
    tree: ast.Module
    imports: dict[str, str] = field(default_factory=dict)
    symbols: list[Symbol] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)


def _module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_files(root: Path) -> list[Path]:
    excluded = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
    return sorted(p for p in root.rglob("*.py") if not excluded.intersection(p.relative_to(root).parts))


def _import_target(module: str, node: ast.ImportFrom, is_package: bool = False) -> str:
    if not node.level:
        return node.module or ""
    package = module.split(".") if is_package else module.split(".")[:-1]
    keep = max(0, len(package) - node.level + 1)
    return ".".join([*package[:keep], *([node.module] if node.module else [])])


def build_index(root: Path) -> dict[str, Module]:
    """Parse repository Python files without importing or executing them."""
    root = root.resolve()
    modules: dict[str, Module] = {}
    for path in _source_files(root):
        relative = path.relative_to(root)
        name = _module_name(relative)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        except (SyntaxError, UnicodeError):
            continue
        module = Module(name=name, file=relative.as_posix(), tree=tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                base = _import_target(name, node, path.stem == "__init__")
                for alias in node.names:
                    if alias.name != "*":
                        module.imports[alias.asname or alias.name] = f"{base}.{alias.name}".strip(".")

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scope: list[str] = []
                self.class_depth = 0

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                qualname = ".".join([*self.scope, node.name])
                module.symbols.append(Symbol(name, qualname, module.file, node.lineno, node.end_lineno or node.lineno, "class"))
                self.scope.append(node.name)
                self.class_depth += 1
                self.generic_visit(node)
                self.class_depth -= 1
                self.scope.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                self._function(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._function(node)

            def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                qualname = ".".join([*self.scope, node.name])
                kind = "method" if self.class_depth and len(self.scope) == self.class_depth else "function"
                module.symbols.append(Symbol(name, qualname, module.file, node.lineno, node.end_lineno or node.lineno, kind))
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def visit_Call(self, node: ast.Call) -> None:
                expression = ast.unparse(node.func)
                kind = "dynamic" if isinstance(node.func, ast.Subscript) or expression.startswith(("getattr(", "globals(", "locals(")) else "direct"
                module.calls.append(Call(name, module.file, node.lineno, ".".join(self.scope) or None, expression, kind))
                self.generic_visit(node)

        Visitor().visit(tree)
        modules[name] = module
    return modules
