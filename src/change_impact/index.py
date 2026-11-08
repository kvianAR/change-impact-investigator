"""Parse Python source without importing or executing repository code."""

from __future__ import annotations

import ast
import copy
import hashlib
import os
import subprocess
import tokenize
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
    start_line: int = 0
    fingerprint: str = ""

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
    shadowed: tuple[str, ...] = ()
    literal_args: tuple[str | None, ...] = ()
    literal_keywords: dict[str, str] = field(default_factory=dict)


@dataclass
class Scope:
    parent: str | None
    kind: str
    imports: dict[str, str] = field(default_factory=dict)
    definitions: dict[str, str] = field(default_factory=dict)
    bindings: set[str] = field(default_factory=set)
    assignments: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    class_owner: str | None = None
    receiver: str | None = None
    constructors: dict[str, str | None] = field(default_factory=dict)


@dataclass
class Module:
    name: str
    file: str
    tree: ast.Module
    imports: dict[str, str] = field(default_factory=dict)
    symbols: list[Symbol] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    scopes: dict[str, Scope] = field(default_factory=dict)
    import_evidence: list[dict] = field(default_factory=list)
    content_hash: str = ""
    ast_hash: str = ""
    binding_hash: str = ""


class RepositoryIndex(dict[str, Module]):
    def __init__(self) -> None:
        super().__init__()
        self.diagnostics: list[dict] = []


def _binding_hash(tree: ast.Module) -> str:
    class WithoutFunctions(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return None

        visit_AsyncFunctionDef = visit_FunctionDef

    projected = WithoutFunctions().visit(copy.deepcopy(tree))
    return hashlib.sha256(ast.dump(projected, include_attributes=False).encode()).hexdigest()


def _module_name(relative: Path, strip_src: bool = True) -> str:
    parts = list(relative.with_suffix("").parts)
    if strip_src and len(parts) > 1 and parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_files(root: Path) -> list[Path]:
    excluded = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
        ".impact-cache",
    }
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.py"],
        cwd=root,
        capture_output=True,
    )
    if proc.returncode == 0:
        paths = [root / os.fsdecode(name) for name in proc.stdout.split(b"\0") if name]
    else:
        paths = []
        for directory, directories, files in os.walk(root):
            directories[:] = [
                name
                for name in directories
                if name not in excluded and not (Path(directory) / name).is_symlink()
            ]
            paths.extend(Path(directory) / name for name in files if name.endswith(".py"))
    return sorted(
        {
            path
            for path in paths
            if path.is_file()
            and not path.is_symlink()
            and not excluded.intersection(path.relative_to(root).parts)
        }
    )


def _import_target(module: str, node: ast.ImportFrom, is_package: bool) -> str:
    if not node.level:
        return node.module or ""
    package = module.split(".") if is_package else module.split(".")[:-1]
    keep = max(0, len(package) - node.level + 1)
    return ".".join([*package[:keep], *([node.module] if node.module else [])])


def _collect_scope(
    module: Module,
    body: list[ast.stmt],
    parent: str | None,
    kind: str,
    qualname: str,
    is_package: bool,
) -> Scope:
    scope = Scope(parent, kind)

    class Bindings(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                scope.bindings.add(node.id)
                scope.assignments.add(node.id)

        def visit_Global(self, node: ast.Global) -> None:
            scope.globals.update(node.names)

        def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
            scope.nonlocals.update(node.names)

        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constructor = (
                        ast.unparse(node.value.func)
                        if isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, (ast.Name, ast.Attribute))
                        else None
                    )
                    scope.constructors[target.id] = (
                        constructor if target.id not in scope.constructors else None
                    )
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name):
                constructor = (
                    ast.unparse(node.value.func)
                    if isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, (ast.Name, ast.Attribute))
                    else None
                )
                scope.constructors[node.target.id] = (
                    constructor if node.target.id not in scope.constructors else None
                )
            self.generic_visit(node)

        def visit_comprehension(self, node: ast.comprehension) -> None:
            self.visit(node.iter)
            for condition in node.ifs:
                self.visit(condition)

        def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            scope.definitions[node.name] = (
                f"{module.name}:{'.'.join(filter(None, [qualname, node.name]))}"
            )

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Lambda(self, node: ast.Lambda) -> None:
            pass

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else alias.name.split(".")[0]
                scope.imports[local] = target
                module.import_evidence.append(
                    {
                        "file": module.file,
                        "line": node.lineno,
                        "scope": qualname or None,
                        "alias": local,
                        "target": target,
                    }
                )

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            base = _import_target(module.name, node, is_package)
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                target = f"{base}.{alias.name}".strip(".")
                scope.imports[local] = target
                module.import_evidence.append(
                    {
                        "file": module.file,
                        "line": node.lineno,
                        "scope": qualname or None,
                        "alias": local,
                        "target": target,
                    }
                )

    visitor = Bindings()
    for statement in body:
        visitor.visit(statement)
    return scope


def build_index(root: Path, sources: dict[str, str] | None = None) -> RepositoryIndex:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")
    index = RepositoryIndex()
    duplicates: set[str] = set()
    paths = (
        _source_files(root)
        if sources is None
        else [root / filename for filename in sorted(sources)]
    )
    strip_src = not (
        (root / "src" / "__init__.py").is_file()
        if sources is None
        else "src/__init__.py" in sources
    )
    for path in paths:
        relative = path.relative_to(root)
        name = _module_name(relative, strip_src)
        if name in index or name in duplicates:
            previous = index.pop(name, None)
            index.diagnostics.append(
                {
                    "file": relative.as_posix(),
                    "line": None,
                    "reason": "duplicate_module_name",
                    "other_file": previous.file if previous else None,
                }
            )
            duplicates.add(name)
            continue
        try:
            if sources is None:
                with tokenize.open(path) as source:
                    text = source.read()
            else:
                text = sources[relative.as_posix()]
            tree = ast.parse(text, filename=str(relative))
        except (SyntaxError, UnicodeError, OSError) as exc:
            index.diagnostics.append(
                {
                    "file": relative.as_posix(),
                    "line": getattr(exc, "lineno", None),
                    "reason": type(exc).__name__,
                }
            )
            continue
        module = Module(name, relative.as_posix(), tree)
        module.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        module.ast_hash = hashlib.sha256(
            ast.dump(tree, include_attributes=False).encode()
        ).hexdigest()
        module.binding_hash = _binding_hash(tree)
        is_package = path.stem == "__init__"
        module.scopes[""] = _collect_scope(module, tree.body, None, "module", "", is_package)
        module.imports = module.scopes[""].imports

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.current = ""
                self.comprehension_names: set[str] = set()
                self.lambda_counts: dict[str, int] = {}

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                for expression in [
                    *node.decorator_list,
                    *node.bases,
                    *(keyword.value for keyword in node.keywords),
                ]:
                    self.visit(expression)
                self._enter(node, "class")

            def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                for expression in [
                    *node.decorator_list,
                    *node.args.defaults,
                    *(value for value in node.args.kw_defaults if value),
                ]:
                    self.visit(expression)
                self._enter(node, "function")

            visit_AsyncFunctionDef = visit_FunctionDef

            def _enter(
                self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str
            ) -> None:
                previous = self.current
                enclosing = module.scopes[previous]
                qualname = ".".join(filter(None, [previous, node.name]))
                symbol_kind = "method" if kind == "function" and enclosing.kind == "class" else kind
                start = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
                fingerprint = hashlib.sha256(
                    ast.dump(node, include_attributes=False).encode()
                ).hexdigest()
                module.symbols.append(
                    Symbol(
                        name,
                        qualname,
                        module.file,
                        node.lineno,
                        node.end_lineno or node.lineno,
                        symbol_kind,
                        start,
                        fingerprint,
                    )
                )
                parent = enclosing.parent if symbol_kind == "method" else previous
                scope = _collect_scope(module, node.body, parent, kind, qualname, is_package)
                if kind == "function":
                    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                    scope.bindings.update(argument.arg for argument in arguments)
                    scope.bindings.update(
                        argument.arg for argument in (node.args.vararg, node.args.kwarg) if argument
                    )
                    is_static = any(
                        isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
                        for decorator in node.decorator_list
                    )
                    if symbol_kind == "method" and arguments and not is_static:
                        scope.class_owner, scope.receiver = previous, arguments[0].arg
                module.scopes[qualname] = scope
                self.current = qualname
                for statement in node.body:
                    self.visit(statement)
                self.current = previous

            def visit_Lambda(self, node: ast.Lambda) -> None:
                for default in [
                    *node.args.defaults,
                    *(value for value in node.args.kw_defaults if value),
                ]:
                    self.visit(default)
                previous = self.current
                ordinal = self.lambda_counts.get(previous, 0) + 1
                self.lambda_counts[previous] = ordinal
                qualname = ".".join(filter(None, [previous, f"<lambda>#{ordinal}"]))
                module.symbols.append(
                    Symbol(
                        name,
                        qualname,
                        module.file,
                        node.lineno,
                        node.end_lineno or node.lineno,
                        "lambda",
                        node.lineno,
                        hashlib.sha256(
                            ast.dump(node, include_attributes=False).encode()
                        ).hexdigest(),
                    )
                )
                scope = Scope(previous, "function")
                scope.bindings.update(
                    arg.arg
                    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                )
                scope.bindings.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg)
                module.scopes[qualname] = scope
                self.current = qualname
                self.visit(node.body)
                self.current = previous

            def visit_ListComp(
                self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
            ) -> None:
                previous = self.comprehension_names.copy()
                for generator in node.generators:
                    self.visit(generator.iter)
                    self.comprehension_names.update(
                        part.id for part in ast.walk(generator.target) if isinstance(part, ast.Name)
                    )
                    for condition in generator.ifs:
                        self.visit(condition)
                expressions = (
                    [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
                )
                for expression in expressions:
                    self.visit(expression)
                self.comprehension_names = previous

            visit_SetComp = visit_ListComp
            visit_DictComp = visit_ListComp
            visit_GeneratorExp = visit_ListComp

            def visit_Call(self, node: ast.Call) -> None:
                expression = ast.unparse(node.func)
                dynamic = isinstance(node.func, (ast.Subscript, ast.Call)) or any(
                    isinstance(part, ast.Call) for part in ast.walk(node.func)
                )
                arguments = tuple(
                    arg.value
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    else None
                    for arg in node.args
                )
                keywords = {
                    item.arg: item.value.value
                    for item in node.keywords
                    if item.arg
                    and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                }
                module.calls.append(
                    Call(
                        name,
                        module.file,
                        node.lineno,
                        self.current or None,
                        expression,
                        "dynamic" if dynamic else "direct",
                        tuple(sorted(self.comprehension_names)),
                        arguments,
                        keywords,
                    )
                )
                self.generic_visit(node)

        Visitor().visit(tree)
        index[name] = module
    return index
