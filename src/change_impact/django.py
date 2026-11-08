"""Static Django URLconf includes, function views, and class HTTP dispatch."""

from __future__ import annotations

import ast

from .index import Call


def discover_django_routes(index):
    from .inheritance import resolve_method
    from .related import HTTP_METHODS, _join_path, _literal
    from .trace import _lookup_name, _resolve

    symbols = {symbol.id: symbol for module in index.values() for symbol in module.symbols}
    configurations, values, roots, diagnostics = {}, {}, [], []
    for module in index.values():
        bindings = {}
        for node in module.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        bindings[target.id] = node.value
                        if target.id == "ROOT_URLCONF" and _literal(node.value):
                            roots.append(_literal(node.value))
            elif (
                isinstance(node, ast.AugAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id in bindings
                and isinstance(node.op, ast.Add)
            ):
                bindings[node.target.id] = ast.BinOp(
                    left=bindings[node.target.id], op=ast.Add(), right=node.value
                )
        values[module.name] = bindings
        if "urlpatterns" in bindings:
            configurations[module.name] = bindings["urlpatterns"]

    def canonical(module, expression):
        root, _, tail = ast.unparse(expression).partition(".")
        return ".".join(filter(None, [_lookup_name(module, "", root), tail]))

    def entries(module, expression, seen=frozenset()):
        if isinstance(expression, (ast.List, ast.Tuple)):
            return expression.elts
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
            return entries(module, expression.left, seen) + entries(module, expression.right, seen)
        if isinstance(expression, ast.Name) and expression.id not in seen:
            value = values[module.name].get(expression.id)
            if value is not None:
                return entries(module, value, seen | {expression.id})
        diagnostics.append(
            {
                "file": module.file,
                "line": getattr(expression, "lineno", None),
                "reason": "dynamic_urlpatterns",
            }
        )
        return []

    included = set()
    for name, expression in configurations.items():
        for node in ast.walk(expression):
            if (
                isinstance(node, ast.Call)
                and canonical(index[name], node.func) == "django.urls.include"
                and node.args
            ):
                child = _literal(node.args[0]) or canonical(index[name], node.args[0])
                if child in configurations:
                    included.add(child)
    explicit_roots = bool(roots)
    roots = roots or sorted(configurations.keys() - included)
    if not roots and configurations:
        diagnostics.append(
            {"file": None, "line": None, "reason": "cyclic_or_unresolved_urlconf_roots"}
        )

    def targets(module, view):
        if isinstance(view, (ast.Name, ast.Attribute)):
            target = _resolve(
                Call(module.name, module.file, view.lineno, None, ast.unparse(view), "direct"),
                module,
                index,
                symbols,
            )
            if target:
                return [{"method": "ANY", "symbol": target}]
        if (
            isinstance(view, ast.Call)
            and isinstance(view.func, ast.Attribute)
            and view.func.attr == "as_view"
        ):
            owner = _resolve(
                Call(
                    module.name,
                    module.file,
                    view.lineno,
                    None,
                    ast.unparse(view.func.value),
                    "direct",
                ),
                module,
                index,
                symbols,
            )
            if owner and symbols[owner].kind == "class":
                dispatch = resolve_method(owner, "dispatch", index, symbols)
                result = []
                for verb in sorted(HTTP_METHODS):
                    method = resolve_method(owner, verb, index, symbols)
                    if method:
                        result.append(
                            {
                                "method": verb.upper(),
                                "symbol": dispatch or method,
                                "dispatch_target": method,
                                "view_class": owner,
                            }
                        )
                return result
        return []

    routes = []

    def visit(module, expression, prefix, chain, trail, root):
        for entry in entries(module, expression):
            if not isinstance(entry, ast.Call) or canonical(module, entry.func) not in {
                "django.urls.path",
                "django.urls.re_path",
            }:
                diagnostics.append(
                    {
                        "file": module.file,
                        "line": getattr(entry, "lineno", None),
                        "reason": "unsupported_django_pattern",
                    }
                )
                continue
            pattern = (
                _literal(entry.args[0])
                if entry.args
                else next(
                    (_literal(item.value) for item in entry.keywords if item.arg == "route"), None
                )
            )
            view = (
                entry.args[1]
                if len(entry.args) > 1
                else next((item.value for item in entry.keywords if item.arg == "view"), None)
            )
            if pattern is None or view is None:
                diagnostics.append(
                    {"file": module.file, "line": entry.lineno, "reason": "dynamic_django_path"}
                )
                continue
            path = _join_path(prefix, pattern)
            evidence = [*chain, {"file": module.file, "line": entry.lineno}]
            if isinstance(view, ast.Call) and canonical(module, view.func) == "django.urls.include":
                child = view.args[0] if view.args else None
                if isinstance(child, ast.Tuple) and child.elts:
                    child = child.elts[0]
                name = (_literal(child) or canonical(module, child)) if child is not None else None
                if name in configurations:
                    if name in trail or len(trail) >= 32:
                        diagnostics.append(
                            {
                                "file": module.file,
                                "line": entry.lineno,
                                "reason": "urlconf_cycle_or_depth_limit",
                            }
                        )
                    else:
                        visit(
                            index[name], configurations[name], path, evidence, trail | {name}, root
                        )
                elif isinstance(child, (ast.List, ast.Tuple)):
                    visit(module, child, path, evidence, trail, root)
                else:
                    diagnostics.append(
                        {
                            "file": module.file,
                            "line": entry.lineno,
                            "reason": "unresolved_django_include",
                        }
                    )
                continue
            resolved = targets(module, view)
            if not resolved:
                diagnostics.append(
                    {"file": module.file, "line": entry.lineno, "reason": "unresolved_django_view"}
                )
            for target in resolved:
                routes.append(
                    {
                        **target,
                        "path": path,
                        "path_is_regex": canonical(module, entry.func) == "django.urls.re_path",
                        "file": module.file,
                        "line": entry.lineno,
                        "framework": "django",
                        "app": f"{root}:urlpatterns",
                        "mount_evidence": evidence,
                        "root_resolution": "settings" if explicit_roots else "urlconf_candidate",
                    }
                )

    for root in roots:
        if root in configurations:
            visit(index[root], configurations[root], "", [], {root}, root)
        else:
            diagnostics.append(
                {"file": None, "line": None, "reason": "missing_root_urlconf", "module": root}
            )
    return routes, diagnostics
