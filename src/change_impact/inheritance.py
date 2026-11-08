"""Static C3 inheritance and super lookup for repository-defined Python classes."""

from __future__ import annotations

import ast

from .index import Module, Symbol


def class_mro(
    class_id: str, index: dict[str, Module], symbols: dict[str, Symbol], trail: tuple[str, ...] = ()
) -> list[str] | None:
    from .trace import _find_target, _lookup_name

    memo = getattr(index, "_memo", {}).setdefault("class_mro", {})
    if class_id in memo:
        return memo[class_id]
    if class_id in trail or class_id not in symbols:
        return None
    module_name, qualname = class_id.split(":", 1)
    module = index[module_name]
    parents = []
    for expression in module.class_bases.get(qualname, []):
        if expression == "object":
            continue
        root, _, rest = expression.partition(".")
        reference = _lookup_name(module, module.scopes[qualname].parent or "", root)
        parent = (
            _find_target(".".join(filter(None, [reference, rest])), index, symbols)
            if reference
            else None
        )
        if parent is None or symbols[parent].kind != "class":
            memo[class_id] = None
            return None
        parents.append(parent)
    sequences = []
    for parent in parents:
        lineage = class_mro(parent, index, symbols, (*trail, class_id))
        if lineage is None:
            return None
        sequences.append(list(lineage))
    sequences.append(list(parents))
    result = [class_id]
    while any(sequences):
        sequences = [sequence for sequence in sequences if sequence]
        candidate = next(
            (
                sequence[0]
                for sequence in sequences
                if all(sequence[0] not in other[1:] for other in sequences)
            ),
            None,
        )
        if candidate is None:
            memo[class_id] = None
            return None
        result.append(candidate)
        for sequence in sequences:
            if sequence[0] == candidate:
                sequence.pop(0)
    memo[class_id] = result
    return result


def resolve_method(
    class_id: str,
    member: str,
    index: dict[str, Module],
    symbols: dict[str, Symbol],
    after: str | None = None,
) -> str | None:
    direct = f"{class_id}.{member}"
    if after is None and direct in symbols:
        return direct
    lineage = class_mro(class_id, index, symbols)
    if lineage is None:
        return None
    if after:
        if after not in lineage:
            return None
        lineage = lineage[lineage.index(after) + 1 :]
    return next((f"{owner}.{member}" for owner in lineage if f"{owner}.{member}" in symbols), None)


def resolve_super(
    expression: str,
    module: Module,
    scope_name: str,
    index: dict[str, Module],
    symbols: dict[str, Symbol],
) -> str | None:
    from .trace import _find_target, _lookup_name

    node = ast.parse(expression, mode="eval").body
    if not (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "super"
    ):
        return None
    scope = module.scopes[scope_name]
    if not scope.class_owner or len(node.value.args) not in {0, 2}:
        return None
    owner = f"{module.name}:{scope.class_owner}"
    after = owner
    if node.value.args:
        first = node.value.args[0]
        receiver = node.value.args[1]
        if (
            not isinstance(first, ast.Name)
            or not isinstance(receiver, ast.Name)
            or receiver.id != scope.receiver
        ):
            return None
        reference = _lookup_name(module, scope_name, first.id)
        after = _find_target(reference, index, symbols) if reference else None
        if after is None:
            return None
    return resolve_method(owner, node.attr, index, symbols, after)
