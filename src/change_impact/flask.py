"""Static Flask application, factory, blueprint, and add_url_rule discovery."""

from __future__ import annotations

import ast

from .index import Call


def discover_flask_routes(index):
    from .related import HTTP_METHODS, _join_path, _keyword, _literal
    from .trace import _lookup_name, _resolve

    objects, containers, mounts, declarations, diagnostics = {}, [], [], [], []
    symbols = {symbol.id: symbol for module in index.values() for symbol in module.symbols}

    def canonical(module, scope, expression):
        root, _, rest = ast.unparse(expression).partition(".")
        reference = _lookup_name(module, scope, root)
        return ".".join(filter(None, [reference, rest]))

    for module in index.values():
        candidates = [("", module.tree.body)]
        for node in module.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returned = {
                    item.value.id
                    for item in node.body
                    if isinstance(item, ast.Return) and isinstance(item.value, ast.Name)
                }
                if returned & module.scopes[node.name].constructors.keys():
                    candidates.append((node.name, node.body))
        for scope, body in candidates:
            containers.append((module, scope, body))
            for node in body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
                    node.value, ast.Call
                ):
                    continue
                kind = canonical(module, scope, node.value.func)
                if kind not in {"flask.Flask", "flask.Blueprint"}:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if (
                        scope
                        and kind == "flask.Flask"
                        and not any(
                            isinstance(item, ast.Return)
                            and isinstance(item.value, ast.Name)
                            and item.value.id == target.id
                            for item in body
                        )
                    ):
                        continue
                    if module.scopes[scope].constructors.get(target.id) is None:
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": node.lineno,
                                "reason": "reassigned_flask_object",
                            }
                        )
                        continue
                    prefix = _keyword(node.value, "url_prefix") or ""
                    if any(
                        item.arg == "url_prefix" and _literal(item.value) is None
                        for item in node.value.keywords
                    ):
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": node.lineno,
                                "reason": "dynamic_flask_prefix",
                            }
                        )
                        continue
                    key = f"{module.name}:{'.'.join(filter(None, [scope, target.id]))}"
                    objects[key] = {
                        "kind": kind,
                        "prefix": prefix,
                        "file": module.file,
                        "line": node.lineno,
                        "factory": f"{module.name}:{scope}" if scope else None,
                    }

    def object_id(module, scope, expression):
        name = ast.unparse(expression)
        for qualified in (".".join(filter(None, [scope, name])), name):
            key = f"{module.name}:{qualified}"
            if key in objects:
                return key
        dotted = canonical(module, scope, expression)
        return next((key for key in objects if key.replace(":", ".") == dotted), None)

    def methods(call, shortcut=None):
        if shortcut:
            return [shortcut.upper()]
        value = next((item.value for item in call.keywords if item.arg == "methods"), None)
        if value is None:
            return ["GET"]
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)) and all(
            _literal(item) for item in value.elts
        ):
            return [_literal(item).upper() for item in value.elts]
        return []

    for module, scope, body in containers:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(
                        decorator.func, ast.Attribute
                    ):
                        continue
                    owner = object_id(module, scope, decorator.func.value)
                    if not owner or decorator.func.attr not in HTTP_METHODS | {"route"}:
                        continue
                    path = (
                        _literal(decorator.args[0])
                        if decorator.args
                        else _keyword(decorator, "rule")
                    )
                    verbs = methods(
                        decorator, decorator.func.attr if decorator.func.attr != "route" else None
                    )
                    if path is None or not verbs:
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": decorator.lineno,
                                "reason": "dynamic_flask_route",
                            }
                        )
                        continue
                    for verb in verbs:
                        declarations.append(
                            {
                                "owner": owner,
                                "method": verb,
                                "path": path,
                                "symbol": f"{module.name}:{'.'.join(filter(None, [scope, node.name]))}",
                                "file": module.file,
                                "line": decorator.lineno,
                            }
                        )
            if (
                not isinstance(node, ast.Expr)
                or not isinstance(node.value, ast.Call)
                or not isinstance(node.value.func, ast.Attribute)
            ):
                continue
            call = node.value
            owner = object_id(module, scope, call.func.value)
            if not owner:
                continue
            if call.func.attr == "register_blueprint":
                expression = (
                    call.args[0]
                    if call.args
                    else next(
                        (item.value for item in call.keywords if item.arg == "blueprint"), None
                    )
                )
                child = object_id(module, scope, expression) if expression is not None else None
                prefix = _keyword(call, "url_prefix")
                dynamic = any(
                    item.arg == "url_prefix" and _literal(item.value) is None
                    for item in call.keywords
                )
                if not child or dynamic:
                    diagnostics.append(
                        {
                            "file": module.file,
                            "line": call.lineno,
                            "reason": "unresolved_blueprint_mount",
                        }
                    )
                else:
                    mounts.append(
                        {
                            "parent": owner,
                            "child": child,
                            "prefix": prefix,
                            "file": module.file,
                            "line": call.lineno,
                        }
                    )
            elif call.func.attr == "add_url_rule":
                path = _literal(call.args[0]) if call.args else _keyword(call, "rule")
                view = next(
                    (item.value for item in call.keywords if item.arg == "view_func"),
                    call.args[2] if len(call.args) > 2 else None,
                )
                target = (
                    _resolve(
                        Call(
                            module.name,
                            module.file,
                            call.lineno,
                            scope or None,
                            ast.unparse(view),
                            "direct",
                        ),
                        module,
                        index,
                        symbols,
                    )
                    if isinstance(view, (ast.Name, ast.Attribute))
                    else None
                )
                verbs = methods(call)
                if path is None or target is None or not verbs:
                    diagnostics.append(
                        {
                            "file": module.file,
                            "line": call.lineno,
                            "reason": "unresolved_flask_view",
                        }
                    )
                else:
                    declarations.extend(
                        {
                            "owner": owner,
                            "method": verb,
                            "path": path,
                            "symbol": target,
                            "file": module.file,
                            "line": call.lineno,
                        }
                        for verb in verbs
                    )

    routes, reached = [], set()

    def visit(owner, prefix, override, chain, seen, app):
        reached.add(owner)
        info = objects[owner]
        current = _join_path(prefix, info["prefix"] if override is None else override)
        for declaration in declarations:
            if declaration["owner"] == owner:
                routes.append(
                    {
                        **declaration,
                        "path": _join_path(current, declaration["path"]),
                        "framework": "flask",
                        "app": app,
                        "factory": objects[app]["factory"],
                        "mount_evidence": chain,
                    }
                )
        for mount in mounts:
            if mount["parent"] != owner:
                continue
            if mount["child"] in seen or len(seen) >= 32:
                diagnostics.append(
                    {
                        "file": mount["file"],
                        "line": mount["line"],
                        "reason": "blueprint_mount_cycle_or_depth_limit",
                    }
                )
                continue
            visit(
                mount["child"],
                current,
                mount["prefix"],
                [*chain, {"file": mount["file"], "line": mount["line"]}],
                seen | {mount["child"]},
                app,
            )

    for key, info in objects.items():
        if info["kind"] == "flask.Flask":
            visit(key, "", None, [], {key}, key)
    for declaration in declarations:
        if declaration["owner"] not in reached:
            diagnostics.append(
                {
                    "file": declaration["file"],
                    "line": declaration["line"],
                    "reason": "unmounted_blueprint",
                }
            )
    return routes, diagnostics
