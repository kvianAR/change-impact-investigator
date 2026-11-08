"""Inspect returned FastAPI application objects inside explicit factory functions."""

from __future__ import annotations

import ast
from dataclasses import replace


def factory_routes(index, discover):
    routes, diagnostics = [], []
    for module in index.values():
        for factory in module.tree.body:
            if not isinstance(factory, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            scope = module.scopes[factory.name]
            returned = {
                node.value.id
                for node in factory.body
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
            }
            candidates = returned & scope.constructors.keys()
            if not candidates:
                continue
            imports = {**module.imports, **scope.imports}
            constructors = []
            for name in candidates:
                root, _, tail = (scope.constructors[name] or "").partition(".")
                constructors.append(".".join(filter(None, [imports.get(root, root), tail])))
            has_app = "fastapi.FastAPI" in constructors
            if not has_app:
                continue
            synthetic_name = f"{module.name}.__factory_{factory.name}"
            virtual = replace(
                module,
                name=synthetic_name,
                tree=ast.Module(body=factory.body, type_ignores=[]),
                imports=imports,
                scopes={"": replace(scope, imports=imports)},
            )
            expanded = {**index, synthetic_name: virtual}
            found, warnings = discover(expanded)
            for route in found:
                if not route["app"].startswith(synthetic_name + ":"):
                    continue
                app_name = route["app"].split(":", 1)[1]
                if app_name not in returned:
                    continue
                handler = route["symbol"]
                if handler.startswith(synthetic_name + ":"):
                    handler = f"{module.name}:{factory.name}.{handler.split(':', 1)[1]}"
                routes.append(
                    {
                        **route,
                        "symbol": handler,
                        "app": f"{module.name}:{factory.name}.{app_name}",
                        "factory": f"{module.name}:{factory.name}",
                        "resolution": "factory_static",
                    }
                )
            diagnostics.extend(
                item
                for item in warnings
                if item["file"] == module.file and item["line"] >= factory.lineno
            )
    return routes, diagnostics
