"""FastAPI dependency providers become explicit call-graph edges."""

from __future__ import annotations

import ast

from .index import Call


def dependency_edges(index, symbols):
    from .related import discover_routes
    from .trace import Edge, _lookup_name, _resolve

    edges, unresolved = [], []
    functions = {}
    by_file = {module.file: module for module in index.values()}
    for module in index.values():
        nodes = {
            node.lineno: node
            for node in ast.walk(module.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for symbol in module.symbols:
            if symbol.line in nodes and symbol.kind in {"function", "method"}:
                functions[symbol.id] = (module, symbol, nodes[symbol.line])

    def collect(module, caller, expressions, scope):
        for expression in expressions:
            for node in ast.walk(expression):
                if not isinstance(node, ast.Call):
                    continue
                root, _, tail = ast.unparse(node.func).partition(".")
                reference = _lookup_name(module, scope, root)
                canonical = ".".join(filter(None, [reference, tail]))
                if canonical not in {"fastapi.Depends", "fastapi.Security"}:
                    continue
                provider = (
                    node.args[0]
                    if node.args
                    else next(
                        (item.value for item in node.keywords if item.arg == "dependency"), None
                    )
                )
                target = None
                if isinstance(provider, (ast.Name, ast.Attribute)):
                    call = Call(
                        module.name,
                        module.file,
                        node.lineno,
                        scope or None,
                        ast.unparse(provider),
                        "direct",
                    )
                    target = _resolve(call, module, index, symbols)
                if target:
                    definition = symbols[target]
                    edges.append(
                        Edge(
                            caller,
                            target,
                            module.file,
                            node.lineno,
                            ast.unparse(node),
                            definition.file,
                            definition.line,
                            "dependency_injection",
                        )
                    )
                else:
                    unresolved.append(
                        {
                            "file": module.file,
                            "line": node.lineno,
                            "caller": caller.split(":", 1)[1],
                            "expression": ast.unparse(node),
                            "reason": "dynamic_or_annotation_only_dependency_provider",
                        }
                    )

    for caller, (module, symbol, node) in functions.items():
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *(value for value in node.args.kw_defaults if value),
            *(arg.annotation for arg in arguments if arg.annotation),
        ]
        collect(module, caller, expressions, module.scopes[symbol.qualname].parent or "")
    for route in discover_routes(index):
        dispatched = route.get("dispatch_target")
        if dispatched and dispatched != route["symbol"]:
            definition = symbols[dispatched]
            edges.append(
                Edge(
                    route["symbol"],
                    dispatched,
                    route["file"],
                    route["line"],
                    "<django HTTP dispatch>",
                    definition.file,
                    definition.line,
                    "framework_dispatch",
                )
            )
        for evidence in route.get("registration_evidence", []):
            module = by_file[evidence["file"]]
            calls = [
                node
                for node in ast.walk(module.tree)
                if isinstance(node, ast.Call) and node.lineno == evidence["line"]
            ]
            scope = next(
                (call.caller or "" for call in module.calls if call.line == evidence["line"]), ""
            )
            collect(module, route["symbol"], calls, scope)
    return list(dict.fromkeys(edges)), list(
        {(item["file"], item["line"], item["caller"]): item for item in unresolved}.values()
    )
