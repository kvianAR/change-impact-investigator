"""Discover supported FastAPI routes and evidence-linked pytest tests."""

from __future__ import annotations

import ast
from dataclasses import asdict

from .index import Module
from .trace import relationships, select_symbol, trace_callers


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _keyword(call: ast.Call, name: str) -> str | None:
    return next((_literal(k.value) for k in call.keywords if k.arg == name), None)


def discover_routes(index: dict[str, Module]) -> list[dict]:
    routers: dict[str, tuple[str, str]] = {}
    inclusions: dict[str, list[str]] = {}
    for module in index.values():
        for node in ast.walk(module.tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                names = [t.id for t in node.targets if isinstance(t, ast.Name)] if isinstance(node, ast.Assign) else ([node.target.id] if isinstance(node.target, ast.Name) else [])
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in {"FastAPI", "APIRouter"}:
                    for name in names:
                        routers[f"{module.name}:{name}"] = (value.func.id, _keyword(value, "prefix") or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router" and node.args:
                if isinstance(node.args[0], ast.Name):
                    local = node.args[0].id
                    imported = module.imports.get(local, f"{module.name}.{local}")
                    inclusions.setdefault(imported, []).append(_keyword(node, "prefix") or "")

    routes: list[dict] = []
    for module in index.values():
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.lower()
                if method not in HTTP_METHODS or not isinstance(decorator.func.value, ast.Name):
                    continue
                owner = decorator.func.value.id
                info = routers.get(f"{module.name}:{owner}")
                path = _literal(decorator.args[0]) if decorator.args else _keyword(decorator, "path")
                if not info or path is None:
                    continue
                prefixes = [""] if info[0] == "FastAPI" else inclusions.get(f"{module.name}.{owner}", [""])
                for included_prefix in prefixes:
                    full_path = "/" + "/".join(part.strip("/") for part in (included_prefix, info[1], path) if part.strip("/"))
                    routes.append({"method": method.upper(), "path": full_path, "symbol": f"{module.name}:{node.name}", "file": module.file, "line": decorator.lineno})
    return routes


def find_related_tests(index: dict[str, Module], query: str, depth: int = 8) -> list[dict]:
    symbols, edges, _ = relationships(index)
    target = select_symbol(symbols, query)
    trace = trace_callers(index, target.id, depth=depth)
    reachable = {target.id}
    reachable.update(path[0]["caller"] for path in trace["paths"])
    impacted_routes = [route for route in discover_routes(index) if route["symbol"] in reachable]
    results: list[dict] = []
    for module in index.values():
        if not (module.file.startswith("tests/") or module.file.startswith("test_") or "/test_" in module.file):
            continue
        for symbol in module.symbols:
            if not symbol.name.startswith("test_"):
                continue
            test_calls = [call for call in module.calls if call.caller == symbol.qualname]
            direct_edges = [edge for edge in edges if edge.caller == symbol.id and edge.target in reachable]
            endpoint_calls = [
                {"file": call.file, "line": call.line, "method": route["method"], "path": route["path"]}
                for call in test_calls for route in impacted_routes
                if call.expression.endswith(f".{route['method'].lower()}")
                and any(isinstance(node, ast.Call) and node.lineno == call.line and any(_literal(arg) == route["path"] for arg in node.args) for node in ast.walk(module.tree))
            ]
            if direct_edges or endpoint_calls:
                results.append({"test": asdict(symbol), "direct_calls": [asdict(edge) for edge in direct_edges], "endpoint_calls": endpoint_calls})
    return results
