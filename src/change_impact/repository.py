"""Select a language backend or combine independent Python and TypeScript graphs."""

from __future__ import annotations

from pathlib import Path

from .index import build_index


def load_index(root: Path, language: str = "python", sources: dict[str, str] | None = None):
    if language not in {"python", "typescript", "auto"}:
        raise ValueError("Language must be python, typescript, or auto")
    if language == "python":
        return build_index(root, sources)
    from .typescript import EXTENSIONS, build_typescript_index, source_files

    if language == "typescript":
        return build_typescript_index(root, sources)
    has_typescript = bool(
        source_files(root)
        if sources is None
        else [name for name in sources if Path(name).suffix in EXTENSIONS]
    )
    if not has_typescript:
        return build_index(root, sources)
    from .related import discover_route_map
    from .trace import relationships

    python = build_index(root, sources)
    typescript = build_typescript_index(root, sources)
    if not python:
        return typescript
    py_symbols, py_edges, py_unresolved = relationships(python)
    ts_symbols, ts_edges, ts_unresolved = relationships(typescript)
    py_routes, py_warnings = discover_route_map(python)
    ts_routes, ts_warnings = discover_route_map(typescript)
    python.update(typescript)
    python.language = "mixed"
    python._memo["relationships"] = (
        {**py_symbols, **ts_symbols},
        py_edges + ts_edges,
        py_unresolved + ts_unresolved,
    )
    python._memo["routes"] = (py_routes + ts_routes, py_warnings + ts_warnings)
    python.typescript_tests = typescript.typescript_tests
    python.diagnostics.extend(typescript.diagnostics)
    python.stats = {
        "parsed_files": python.stats["parsed_files"] + typescript.stats["parsed_files"],
        "cache_hits": python.stats["cache_hits"] + typescript.stats["cache_hits"],
        "backends": {"python": python.stats, "typescript": typescript.stats},
    }
    return python
