"""Resolve supported Python calls and trace callers with source evidence."""

from __future__ import annotations

import builtins
from collections import defaultdict, deque
from dataclasses import asdict, dataclass

from .index import Call, Module, Symbol


@dataclass(frozen=True)
class Edge:
    caller: str
    target: str
    file: str
    line: int
    expression: str
    target_file: str
    target_line: int
    resolution: str = "static"


def _lookup_name(module: Module, scope_name: str, name: str) -> str | None:
    current: str | None = scope_name
    while current is not None:
        scope = module.scopes[current]
        if current and name in scope.globals:
            if name in scope.assignments:
                return None
            current = ""
            continue
        if name in scope.nonlocals:
            if name in scope.assignments:
                return None
            current = scope.parent
            continue
        if name in scope.assignments:
            return None
        if name in scope.imports:
            return scope.imports[name]
        if name in scope.definitions:
            return scope.definitions[name]
        if name in scope.bindings:
            return None
        current = scope.parent
    return None


def _instance_type(module: Module, scope_name: str, name: str) -> str | None:
    current: str | None = scope_name
    while current is not None:
        scope = module.scopes[current]
        if name in scope.assignments:
            constructor = scope.constructors.get(name)
            if not constructor:
                return None
            root, _, rest = constructor.partition(".")
            target = _lookup_name(module, current, root)
            return ".".join(filter(None, [target, rest])) if target else None
        if name in scope.bindings:
            return None
        current = scope.parent
    return None


def _find_target(target: str, index: dict[str, Module], symbols: dict[str, Symbol], visited: set[str] | None = None) -> str | None:
    if target in symbols:
        return target
    visited = visited or set()
    if target in visited:
        return None
    visited.add(target)
    parts = target.split(".")
    for split in range(len(parts) - 1, 0, -1):
        module_name, rest = ".".join(parts[:split]), ".".join(parts[split:])
        candidate = f"{module_name}:{rest}"
        if candidate in symbols:
            return candidate
        module = index.get(module_name)
        if module and rest.split(".")[0] in module.imports:
            head, _, tail = rest.partition(".")
            redirected = ".".join(filter(None, [module.imports[head], tail]))
            found = _find_target(redirected, index, symbols, visited)
            if found:
                return found
    return None


def _resolve(call: Call, module: Module, index: dict[str, Module], symbols: dict[str, Symbol]) -> str | None:
    if call.kind == "dynamic":
        return None
    root, separator, rest = call.expression.partition(".")
    if root in call.shadowed:
        return None
    scope_name = call.caller or ""
    current: str | None = scope_name
    while separator and current is not None:
        scope = module.scopes[current]
        if root == scope.receiver and root not in scope.assignments:
            candidate = f"{module.name}:{scope.class_owner}.{rest}"
            return candidate if candidate in symbols else None
        if root in scope.bindings or root in scope.assignments:
            break
        current = scope.parent
    target = _lookup_name(module, scope_name, root)
    if target is None and separator:
        target = _instance_type(module, scope_name, root)
    if target is None:
        return None
    if separator:
        target = f"{target}.{rest}"
    return _find_target(target, index, symbols)


def relationships(index: dict[str, Module]) -> tuple[dict[str, Symbol], list[Edge], list[dict]]:
    symbols = {symbol.id: symbol for module in index.values() for symbol in module.symbols}
    edges: list[Edge] = []
    unresolved: list[dict] = []
    for module in index.values():
        for call in module.calls:
            target = _resolve(call, module, index, symbols)
            if target:
                definition = symbols[target]
                root = call.expression.split(".", 1)[0]
                resolution = "constructor_inference" if _instance_type(module, call.caller or "", root) else "static"
                edges.append(Edge(f"{module.name}:{call.caller or '<module>'}", target, call.file, call.line, call.expression, definition.file, definition.line, resolution))
                continue
            root = call.expression.split(".", 1)[0]
            external = _lookup_name(module, call.caller or "", root) or _instance_type(module, call.caller or "", root)
            internal = bool(external) and any(name and (external == name or external.startswith(name + ".") or external.startswith(name + ":")) for name in index)
            if call.kind == "dynamic" or root in call.shadowed or internal or (external is None and root not in vars(builtins)):
                unresolved.append({"file": call.file, "line": call.line, "caller": call.caller, "expression": call.expression, "reason": "runtime-selected or unresolved call target"})
    return symbols, edges, unresolved


def select_symbol(symbols: dict[str, Symbol], query: str) -> Symbol:
    if query in symbols:
        return symbols[query]
    matches = [symbol for symbol in symbols.values() if symbol.name == query or symbol.qualname == query]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"Symbol not found: {query}")
    raise ValueError(f"Ambiguous symbol {query!r}; use one of: {', '.join(sorted(symbol.id for symbol in matches))}")


def trace_callers(index: dict[str, Module], query: str, depth: int = 3) -> dict:
    if not 1 <= depth <= 32:
        raise ValueError("Depth must be between 1 and 32")
    symbols, edges, unresolved = relationships(index)
    target = select_symbol(symbols, query)
    incoming: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        incoming[edge.target].append(edge)
    paths: list[list[dict]] = []
    frontier = deque([(target.id, [], {target.id})])
    truncated = False
    while frontier:
        current, path, visited = frontier.popleft()
        if len(path) >= depth:
            truncated = truncated or bool(incoming[current])
            continue
        for edge in incoming[current]:
            new_path = [edge, *path]
            paths.append([asdict(item) for item in new_path])
            if len(paths) >= 500:
                truncated = True
                frontier.clear()
                break
            if edge.caller not in visited:
                frontier.append((edge.caller, new_path, visited | {edge.caller}))
    dotted = f"{target.module}.{target.qualname}"
    imports = [item for module in index.values() for item in module.import_evidence if dotted.startswith(item["target"] + ".") or _find_target(item["target"], index, symbols) == target.id]
    return {
        "symbol": asdict(target), "paths": paths, "imports": imports,
        "unresolved_dynamic_calls": unresolved,
        "diagnostics": getattr(index, "diagnostics", []), "truncated": truncated, "depth": depth,
    }
