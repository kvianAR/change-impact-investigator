"""Resolve supported Python calls and trace callers with source evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .index import Call, Module, Symbol


@dataclass(frozen=True)
class Edge:
    caller: str
    target: str
    file: str
    line: int
    expression: str


def _resolve(call: Call, module: Module, symbols: dict[str, Symbol]) -> str | None:
    expression = call.expression
    if call.kind == "dynamic":
        return None
    if expression in module.imports:
        target = module.imports[expression]
    elif expression.startswith(("self.", "cls.")) and call.caller and "." in call.caller:
        target = f"{module.name}:{call.caller.rsplit('.', 1)[0]}.{expression.split('.', 1)[1]}"
        return target if target in symbols else None
    elif "." in expression:
        root, rest = expression.split(".", 1)
        target = f"{module.imports[root]}.{rest}" if root in module.imports else ""
    else:
        target = f"{module.name}:{expression}"
        if call.caller:
            scopes = call.caller.split(".")[:-1]
            while scopes:
                scoped = f"{module.name}:{'.'.join([*scopes, expression])}"
                if scoped in symbols:
                    return scoped
                scopes.pop()
        return target if target in symbols else None
    if ":" not in target:
        parts = target.split(".")
        for split in range(len(parts) - 1, 0, -1):
            candidate = f"{'.'.join(parts[:split])}:{'.'.join(parts[split:])}"
            if candidate in symbols:
                return candidate
    return target if target in symbols else None


def relationships(index: dict[str, Module]) -> tuple[dict[str, Symbol], list[Edge], list[dict]]:
    symbols = {s.id: s for module in index.values() for s in module.symbols}
    edges: list[Edge] = []
    unresolved: list[dict] = []
    for module in index.values():
        for call in module.calls:
            target = _resolve(call, module, symbols)
            if target and call.caller:
                edges.append(Edge(f"{module.name}:{call.caller}", target, call.file, call.line, call.expression))
            elif call.kind == "dynamic":
                unresolved.append({"file": call.file, "line": call.line, "caller": call.caller, "expression": call.expression, "reason": "runtime-selected call target"})
    return symbols, edges, unresolved


def select_symbol(symbols: dict[str, Symbol], query: str) -> Symbol:
    if query in symbols:
        return symbols[query]
    matches = [s for s in symbols.values() if s.name == query or s.qualname == query]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"Symbol not found: {query}")
    raise ValueError(f"Ambiguous symbol {query!r}; use one of: {', '.join(sorted(s.id for s in matches))}")


def trace_callers(index: dict[str, Module], query: str, depth: int = 3) -> dict:
    symbols, edges, unresolved = relationships(index)
    target = select_symbol(symbols, query)
    paths: list[list[dict]] = []
    frontier: list[tuple[str, list[Edge]]] = [(target.id, [])]
    seen = {target.id}
    for _ in range(max(0, depth)):
        next_frontier = []
        for current, path in frontier:
            for edge in edges:
                if edge.target != current:
                    continue
                new_path = [edge, *path]
                paths.append([asdict(item) for item in new_path])
                if edge.caller not in seen:
                    next_frontier.append((edge.caller, new_path))
                    seen.add(edge.caller)
        frontier = next_frontier
    return {"symbol": asdict(target), "paths": paths, "unresolved_dynamic_calls": unresolved}
