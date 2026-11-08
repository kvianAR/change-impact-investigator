"""Discover mounted FastAPI routes and evidence-linked pytest tests."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .index import Call, Module
from .trace import relationships, select_symbol, trace_callers

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _literal(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _keyword(call: ast.Call, name: str) -> str | None:
    return next((_literal(item.value) for item in call.keywords if item.arg == name), None)


def _canonical(module: Module, expression: ast.AST) -> str:
    head, _, tail = ast.unparse(expression).partition(".")
    scope = module.scopes[""]
    target = (
        head
        if head in scope.assignments or head in scope.definitions
        else module.imports.get(head, head)
    )
    return ".".join(filter(None, [target, tail]))


def _join_path(*parts: str) -> str:
    path = "/" + "/".join(part.strip("/") for part in parts if part.strip("/"))
    return path + "/" if path != "/" and parts[-1].endswith("/") else path


def _discover_route_map(index: dict[str, Module]) -> tuple[list[dict], list[dict]]:
    objects: dict[str, dict] = {}
    mounts: list[dict] = []
    declarations: list[dict] = []
    diagnostics: list[dict] = []
    for module in index.values():
        for node in module.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                constructor = _canonical(module, node.value.func)
                if constructor not in {"fastapi.FastAPI", "fastapi.APIRouter"}:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                prefix = _keyword(node.value, "prefix") or ""
                if any(
                    item.arg == "prefix" and _literal(item.value) is None
                    for item in node.value.keywords
                ):
                    diagnostics.append(
                        {
                            "file": module.file,
                            "line": node.lineno,
                            "reason": "dynamic_router_prefix",
                        }
                    )
                    continue
                for target in targets:
                    if isinstance(target, ast.Name):
                        if module.scopes[""].constructors.get(target.id) is None:
                            diagnostics.append(
                                {
                                    "file": module.file,
                                    "line": node.lineno,
                                    "reason": "reassigned_router_variable",
                                }
                            )
                            continue
                        objects[f"{module.name}:{target.id}"] = {
                            "kind": constructor,
                            "prefix": prefix,
                            "file": module.file,
                            "line": node.lineno,
                        }

    def object_id(module: Module, expression: ast.AST) -> str | None:
        local = f"{module.name}:{ast.unparse(expression)}"
        if local in objects:
            return local
        dotted = _canonical(module, expression)
        return next((key for key in objects if key.replace(":", ".") == dotted), None)

    for module in index.values():
        top_mounts: set[int] = set()
        for node in module.tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == "include_router":
                    top_mounts.add(id(call))
                    parent = object_id(module, call.func.value)
                    child_expression = (
                        call.args[0]
                        if call.args
                        else next(
                            (item.value for item in call.keywords if item.arg == "router"), None
                        )
                    )
                    child = (
                        object_id(module, child_expression)
                        if child_expression is not None
                        else None
                    )
                    dynamic_prefix = any(
                        item.arg == "prefix" and _literal(item.value) is None
                        for item in call.keywords
                    )
                    if not parent or not child or dynamic_prefix:
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": call.lineno,
                                "reason": "unresolved_router_mount",
                            }
                        )
                    else:
                        mounts.append(
                            {
                                "parent": parent,
                                "child": child,
                                "prefix": _keyword(call, "prefix") or "",
                                "file": module.file,
                                "line": call.lineno,
                            }
                        )
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(
                    decorator.func, ast.Attribute
                ):
                    continue
                method = decorator.func.attr.lower()
                if method not in HTTP_METHODS | {"api_route", "route"}:
                    continue
                owner = object_id(module, decorator.func.value)
                if owner is None:
                    continue
                path = (
                    _literal(decorator.args[0]) if decorator.args else _keyword(decorator, "path")
                )
                if not owner or path is None:
                    diagnostics.append(
                        {
                            "file": module.file,
                            "line": decorator.lineno,
                            "reason": "unresolved_route_declaration",
                        }
                    )
                    continue
                methods = [method.upper()]
                if method in {"api_route", "route"}:
                    methods_node = next(
                        (item.value for item in decorator.keywords if item.arg == "methods"), None
                    )
                    methods = (
                        [_literal(item) for item in methods_node.elts]
                        if isinstance(methods_node, (ast.List, ast.Tuple, ast.Set))
                        else (["GET"] if methods_node is None else [])
                    )
                    if not methods or any(item is None for item in methods):
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": decorator.lineno,
                                "reason": "dynamic_route_methods",
                            }
                        )
                        continue
                for http_method in methods:
                    declarations.append(
                        {
                            "owner": owner,
                            "method": http_method.upper(),
                            "path": path,
                            "symbol": f"{module.name}:{node.name}",
                            "file": module.file,
                            "line": decorator.lineno,
                        }
                    )
        for node in ast.walk(module.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
                and id(node) not in top_mounts
            ):
                diagnostics.append(
                    {
                        "file": module.file,
                        "line": node.lineno,
                        "reason": "conditional_or_dynamic_router_mount",
                    }
                )

    routes: list[dict] = []
    reached: set[str] = set()

    def visit(owner: str, prefix: str, chain: list[dict], seen: set[str], app: str) -> None:
        reached.add(owner)
        current_prefix = _join_path(prefix, objects[owner]["prefix"])
        for declaration in declarations:
            if declaration["owner"] == owner:
                routes.append(
                    {
                        **declaration,
                        "path": _join_path(current_prefix, declaration["path"]),
                        "app": app,
                        "mount_evidence": chain,
                        "registration_evidence": [
                            {"file": objects[key]["file"], "line": objects[key]["line"]}
                            for key in sorted(seen)
                        ]
                        + chain,
                    }
                )
        for mount in mounts:
            if mount["parent"] != owner:
                continue
            if mount["child"] in seen or len(seen) >= 32:
                reason = (
                    "router_mount_cycle" if mount["child"] in seen else "router_mount_depth_limit"
                )
                diagnostics.append({"file": mount["file"], "line": mount["line"], "reason": reason})
                continue
            visit(
                mount["child"],
                _join_path(current_prefix, mount["prefix"]),
                [*chain, {"file": mount["file"], "line": mount["line"]}],
                seen | {mount["child"]},
                app,
            )

    for owner, info in objects.items():
        if info["kind"] == "fastapi.FastAPI":
            visit(owner, "", [], {owner}, owner)
    for declaration in declarations:
        if declaration["owner"] not in reached:
            diagnostics.append(
                {
                    "file": declaration["file"],
                    "line": declaration["line"],
                    "reason": "unmounted_router",
                }
            )
    return routes, diagnostics


def discover_route_map(index: dict[str, Module]) -> tuple[list[dict], list[dict]]:
    memo = getattr(index, "_memo", None)
    if memo is None:
        return _all_route_map(index)
    if "routes" not in memo:
        memo["routes"] = _all_route_map(index)
        index.stats["route_builds"] = index.stats.get("route_builds", 0) + 1
    return memo["routes"]


def _all_route_map(index):
    from .django import discover_django_routes
    from .factories import factory_routes
    from .flask import discover_flask_routes

    routes, diagnostics = _discover_route_map(index)
    factory_found, factory_warnings = factory_routes(index, _discover_route_map)
    flask_found, flask_warnings = discover_flask_routes(index)
    django_found, django_warnings = discover_django_routes(index)
    mounted = {(route["file"], route["line"]) for route in factory_found}
    registrations = {
        (item["file"], item["line"])
        for route in factory_found
        for item in route.get("mount_evidence", [])
    }
    diagnostics = [
        item
        for item in diagnostics
        if not (item["reason"] == "unmounted_router" and (item["file"], item["line"]) in mounted)
        and not (
            item["reason"] == "conditional_or_dynamic_router_mount"
            and (item["file"], item["line"]) in registrations
        )
    ]
    return (
        routes + factory_found + flask_found + django_found,
        diagnostics + factory_warnings + flask_warnings + django_warnings,
    )


def discover_routes(index: dict[str, Module]) -> list[dict]:
    return discover_route_map(index)[0]


def _path_matches(template: str, url: str) -> bool:
    template = re.sub(
        r"<(?:(\w+):)?(\w+)>",
        lambda match: "{" + match.group(2) + (":path" if match.group(1) == "path" else "") + "}",
        template,
    )
    parts = re.split(r"(\{[^{}]+\})", template)
    pattern = "".join(
        (".*" if part.endswith(":path}") else "[^/]+")
        if part.startswith("{") and part.endswith("}")
        else re.escape(part)
        for part in parts
    )
    return re.fullmatch(pattern, urlsplit(url).path) is not None


def _http_call(call: Call) -> tuple[str, str] | None:
    method = call.expression.rsplit(".", 1)[-1].lower()
    arguments = call.literal_args
    if method == "request":
        http_method = arguments[0] if arguments else call.literal_keywords.get("method")
        path = arguments[1] if len(arguments) > 1 else call.literal_keywords.get("url")
    else:
        http_method = method.upper() if method in HTTP_METHODS else None
        path = arguments[0] if arguments else call.literal_keywords.get("url")
    return (http_method.upper(), path) if http_method and path is not None else None


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [
        argument.arg
        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if argument.arg not in {"self", "cls"}
    ]


def _fixtures(index: dict[str, Module]) -> list[dict]:
    result = []
    for module in index.values():
        for node in module.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                expression = decorator.func if isinstance(decorator, ast.Call) else decorator
                if _canonical(module, expression) != "pytest.fixture":
                    continue
                fixture_name = (
                    _keyword(decorator, "name") if isinstance(decorator, ast.Call) else None
                ) or node.name
                autouse = isinstance(decorator, ast.Call) and any(
                    item.arg == "autouse"
                    and isinstance(item.value, ast.Constant)
                    and item.value.value is True
                    for item in decorator.keywords
                )
                result.append(
                    {
                        "name": fixture_name,
                        "symbol": f"{module.name}:{node.name}",
                        "module": module.name,
                        "file": module.file,
                        "line": node.lineno,
                        "parameters": _parameters(node),
                        "autouse": autouse,
                    }
                )
    return result


def _fixture_links(
    module: Module,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    fixtures: list[dict],
    reachable: set[str],
    depth: int,
) -> list[dict]:
    test_directory = PurePosixPath(module.file).parent

    def provider(name: str) -> dict | None:
        candidates = []
        for fixture in fixtures:
            imported = module.imports.get(name) == fixture["symbol"].replace(":", ".")
            local = fixture["file"] == module.file
            directory = PurePosixPath(fixture["file"]).parent
            inherited = PurePosixPath(fixture["file"]).name == "conftest.py" and (
                directory == test_directory or directory in test_directory.parents
            )
            if (fixture["name"] == name and (local or inherited)) or imported:
                candidates.append(
                    (10000 if local else 9000 if imported else len(directory.parts), fixture)
                )
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    requested = [(name, "pytest_parameter") for name in _parameters(node)]
    for fixture in fixtures:
        if fixture["autouse"] and provider(fixture["name"]) == fixture:
            requested.append((fixture["name"], "autouse_fixture"))
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and _canonical(module, decorator.func) == "pytest.mark.usefixtures"
        ):
            requested.extend(
                (name, "usefixtures_marker")
                for argument in decorator.args
                if (name := _literal(argument))
            )
    links = []
    queue = [(name, reason, []) for name, reason in requested]
    visited: set[str] = set()
    while queue:
        name, reason, path = queue.pop(0)
        fixture = provider(name)
        if not fixture or fixture["symbol"] in visited or len(path) >= depth:
            continue
        visited.add(fixture["symbol"])
        chain = [*path, {"name": name, "file": fixture["file"], "line": fixture["line"]}]
        if fixture["symbol"] in reachable:
            links.append({"fixture": fixture, "path": chain, "reason": reason})
        queue.extend((dependency, reason, chain) for dependency in fixture["parameters"])
    return links


def find_related_tests(index: dict[str, Module], query: str, depth: int = 8) -> list[dict]:
    symbols, edges, _ = relationships(index)
    target = select_symbol(symbols, query)
    trace = trace_callers(index, target.id, depth)
    reachable = {target.id, *(path[0]["caller"] for path in trace["paths"])}
    routes = [route for route in discover_routes(index) if route["symbol"] in reachable]
    fixtures = _fixtures(index)
    results = []
    for module in index.values():
        filename = PurePosixPath(module.file).name
        if not (filename.startswith("test_") or filename.endswith("_test.py")):
            continue
        nodes = {
            node.lineno: node
            for node in ast.walk(module.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for symbol in module.symbols:
            if not symbol.name.startswith("test_") or any(
                not parent.startswith("Test") for parent in symbol.qualname.split(".")[:-1]
            ):
                continue
            node = nodes[symbol.line]
            direct_edges = [
                edge for edge in edges if edge.caller == symbol.id and edge.target in reachable
            ]
            endpoint_calls = []
            for call in module.calls:
                if call.caller != symbol.qualname or (request := _http_call(call)) is None:
                    continue
                for route in routes:
                    if (
                        route["method"] in {request[0], "ANY"}
                        and not route.get("path_is_regex")
                        and _path_matches(route["path"], request[1])
                    ):
                        endpoint_calls.append(
                            {
                                "file": call.file,
                                "line": call.line,
                                "method": request[0],
                                "path": request[1],
                                "route_file": route["file"],
                                "route_line": route["line"],
                                "reason": "http_path_candidate",
                            }
                        )
            fixture_links = _fixture_links(module, node, fixtures, reachable, depth)
            if direct_edges or endpoint_calls or fixture_links:
                results.append(
                    {
                        "test": asdict(symbol),
                        "direct_calls": [asdict(edge) for edge in direct_edges],
                        "endpoint_calls": endpoint_calls,
                        "fixture_dependencies": fixture_links,
                        "confidence": "static" if direct_edges or fixture_links else "candidate",
                    }
                )
    return results
