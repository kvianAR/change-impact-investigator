"""Map working tree changes to current and historical Python evidence."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .git import Change, diff_changes, read_revision_sources, repository_root, resolve_base
from .index import Module, Symbol, failed_source_files
from .related import discover_route_map, discover_routes, find_related_tests
from .repository import load_index
from .trace import relationships, select_symbol, trace_callers


def changed_lines(root: Path) -> dict[str, set[int]]:
    root = repository_root(root)
    return {
        change.file: change.new_lines
        for change in diff_changes(root, resolve_base(root, "HEAD"))
        if change.file.endswith(".py")
    }


def _affected(
    index: dict[str, Module], changes: list[Change], state: str
) -> tuple[dict[str, str], list[dict]]:
    affected: dict[str, str] = {}
    module_changes: list[dict] = []
    by_file = {module.file: module for module in index.values()}
    for change in changes:
        module = by_file.get(change.file)
        if module is None:
            continue
        lines = change.old_lines if state == "base" else change.new_lines
        functions = [symbol for symbol in module.symbols if symbol.kind != "class"]
        for symbol in functions:
            if any((symbol.start_line or symbol.line) <= line <= symbol.end_line for line in lines):
                affected[symbol.id] = "symbol_source_changed"
        uncovered = {
            line
            for line in lines
            if not any(
                (symbol.start_line or symbol.line) <= line <= symbol.end_line
                for symbol in functions
            )
        }
        if uncovered:
            module_changes.append(
                {"file": change.file, "lines": sorted(uncovered), "evidence_state": state}
            )
            for symbol in functions:
                affected.setdefault(symbol.id, "module_level_change")
    return affected, module_changes


def _symbol_report(
    index: dict[str, Module], target: Symbol, reason: str, state: str, depth: int
) -> dict:
    trace = trace_callers(index, target.id, depth)
    reachable = {target.id, *(path[0]["caller"] for path in trace["paths"])}
    return {
        "symbol": asdict(target),
        "reason": reason,
        "evidence_state": state,
        "caller_paths": trace["paths"],
        "imports": trace["imports"],
        "affected_routes": [
            route for route in discover_routes(index) if route["symbol"] in reachable
        ],
        "related_tests": find_related_tests(index, target.id, depth),
        "truncated": trace["truncated"],
    }


def inspect_change_impact(
    root: Path,
    symbol: str | None = None,
    base: str = "HEAD",
    depth: int = 8,
    language: str = "python",
) -> dict:
    if not 1 <= depth <= 32:
        raise ValueError("Depth must be between 1 and 32")
    root = repository_root(root)
    base_commit = resolve_base(root, base)
    changes = diff_changes(root, base_commit)
    index = load_index(root, language)
    symbols, _, unresolved = relationships(index)
    current_affected, module_changes = _affected(index, changes, "working_tree")
    selected_suffixes = (
        {".py"}
        if language == "python"
        else {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    )
    if language == "auto":
        selected_suffixes.add(".py")
    configuration_changes = [
        change.file
        for change in changes
        if language != "python"
        and (
            (Path(change.file).name.startswith("tsconfig") and change.file.endswith(".json"))
            or Path(change.file).name
            in {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
        )
    ]
    if configuration_changes:
        current_affected.update(
            {
                item.id: "typescript_configuration_change"
                for module in index.values()
                if module.language == "typescript"
                for item in module.symbols
                if item.kind != "class"
            }
        )
    old_index: dict[str, Module] = {}
    old_symbols: dict[str, Symbol] = {}
    old_affected: dict[str, str] = {}
    non_semantic_files: set[str] = set()
    diagnostics = list(index.diagnostics)
    failed_files = failed_source_files(index)
    diagnostics.extend({**item, "state": "working_tree"} for item in discover_route_map(index)[1])
    if base_commit and (
        symbol is None
        or not any(symbol in {item.id, item.name, item.qualname} for item in symbols.values())
    ):
        sources, read_diagnostics = read_revision_sources(root, base_commit)
        old_index = load_index(root, language, sources)
        old_symbols, _, _ = relationships(old_index)
        old_affected, old_module_changes = _affected(old_index, changes, "base")
        if configuration_changes:
            old_affected.update(
                {
                    item.id: "typescript_configuration_change"
                    for module in old_index.values()
                    if module.language == "typescript"
                    for item in module.symbols
                    if item.kind != "class"
                }
            )
        module_changes.extend(old_module_changes)
        diagnostics.extend(read_diagnostics)
        diagnostics.extend({**item, "state": "base"} for item in old_index.diagnostics)
        diagnostics.extend({**item, "state": "base"} for item in discover_route_map(old_index)[1])
        old_by_file = {module.file: module for module in old_index.values()}
        non_semantic_files = {
            module.file
            for module in index.values()
            if module.file in old_by_file and module.ast_hash == old_by_file[module.file].ast_hash
        }
        non_semantic_files.intersection_update(change.file for change in changes)
        shared_files = {module.file for module in index.values()} & old_by_file.keys()
        binding_changes = {
            module.file
            for module in index.values()
            if module.file in shared_files
            and module.binding_hash != old_by_file[module.file].binding_hash
        }

        def meaningful(target_id: str, reason: str) -> str | None:
            if reason == "typescript_configuration_change":
                return reason
            current_symbol, old_symbol = symbols.get(target_id), old_symbols.get(target_id)
            if not current_symbol or not old_symbol or current_symbol.file in binding_changes:
                return reason
            return (
                "symbol_source_changed"
                if current_symbol.fingerprint != old_symbol.fingerprint
                else None
            )

        current_affected = {
            key: updated
            for key, reason in current_affected.items()
            if (updated := meaningful(key, reason))
        }
        old_affected = {
            key: updated
            for key, reason in old_affected.items()
            if (updated := meaningful(key, reason))
        }
        module_changes = [
            item
            for item in module_changes
            if item["file"] not in shared_files or item["file"] in binding_changes
        ]
    reports: list[dict] = []
    if symbol:
        if symbol in symbols or any(
            symbol in {item.name, item.qualname} for item in symbols.values()
        ):
            target = select_symbol(symbols, symbol)
            reports.append(_symbol_report(index, target, "selected_symbol", "working_tree", depth))
        else:
            target = select_symbol(old_symbols, symbol)
            reason = (
                "current_source_unparseable" if target.file in failed_files else "removed_symbol"
            )
            reports.append(_symbol_report(old_index, target, reason, "base", depth))
    else:
        for target_id in sorted(current_affected.keys() | old_affected.keys()):
            if target_id in symbols:
                reason = current_affected.get(
                    target_id, old_affected.get(target_id, "symbol_source_changed")
                )
                reports.append(
                    _symbol_report(index, symbols[target_id], reason, "working_tree", depth)
                )
            elif target_id in old_symbols:
                reason = (
                    "current_source_unparseable"
                    if old_symbols[target_id].file in failed_files
                    else "removed_symbol"
                )
                reports.append(
                    _symbol_report(old_index, old_symbols[target_id], reason, "base", depth)
                )
    return {
        "schema_version": 1,
        "language": language,
        "index_stats": dict(index.stats),
        "repository": str(root),
        "base": base,
        "base_commit": base_commit,
        "depth": depth,
        "changed_files": [
            change.file for change in changes if Path(change.file).suffix in selected_suffixes
        ],
        "configuration_changes": configuration_changes,
        "unsupported_changed_files": [
            change.file
            for change in changes
            if Path(change.file).suffix not in selected_suffixes
            and change.file not in configuration_changes
        ],
        "non_semantic_changed_files": sorted(non_semantic_files),
        "impacts": reports,
        "module_level_changes": module_changes,
        "source_hashes": {module.file: module.content_hash for module in index.values()},
        "unresolved_dynamic_calls": unresolved,
        "unresolved_scope": "repository",
        "diagnostics": diagnostics,
        "limits": [
            "Static call paths indicate possible impact. Runtime dispatch can remain unresolved.",
            f"Caller traversal is limited to depth {depth} and 500 paths per symbol.",
        ],
    }
