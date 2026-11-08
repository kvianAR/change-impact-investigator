"""Optional TypeScript compiler backend, executed through a trusted Node runtime."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .cache import IndexCache
from .index import Module, RepositoryIndex, Scope, Symbol
from .trace import Edge

EXTENSIONS = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}


def source_files(root: Path) -> list[str]:
    patterns = [f"*{extension}" for extension in sorted(EXTENSIONS)]
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *patterns],
        cwd=root,
        capture_output=True,
    )
    excluded = {"node_modules", ".git", ".impact-cache", "dist", "build", ".venv"}
    if result.returncode == 0:
        paths = [root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name]
    else:
        paths = []
        for directory, directories, names in os.walk(root):
            directories[:] = [
                name
                for name in directories
                if name not in excluded and not (Path(directory) / name).is_symlink()
            ]
            paths.extend(
                Path(directory) / name for name in names if Path(name).suffix in EXTENSIONS
            )
    return sorted(
        {
            path.relative_to(root).as_posix()
            for path in paths
            if path.is_file()
            and not path.is_symlink()
            and not excluded.intersection(path.relative_to(root).parts)
        }
    )


def compiler_path() -> Path:
    configured = os.environ.get("CHANGE_IMPACT_TYPESCRIPT_PATH")
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_dir():
            path = path / "lib/typescript.js"
        if path.is_file():
            return path
        raise ValueError("CHANGE_IMPACT_TYPESCRIPT_PATH does not point to a TypeScript compiler")
    for directory in Path(__file__).resolve().parents:
        candidate = directory / "node_modules/typescript/lib/typescript.js"
        if candidate.is_file():
            return candidate
    executable = shutil.which("tsc")
    if executable:
        candidate = Path(executable).resolve().parents[1] / "lib/typescript.js"
        if candidate.is_file():
            return candidate
    raise ValueError(
        "Install the trusted TypeScript runtime with npm ci in the tool checkout, or set CHANGE_IMPACT_TYPESCRIPT_PATH"
    )


def _valid_inputs(payload: dict, own: set[str]) -> bool:
    try:
        for filename, expected in payload["inputs"].items():
            if filename not in own:
                text = Path(filename).read_bytes().decode("utf-8-sig")
                if hashlib.sha256(text.encode()).hexdigest() != expected:
                    return False
        return not any(Path(filename).exists() for filename in payload.get("missing_inputs", []))
    except (OSError, UnicodeError, KeyError, TypeError, ValueError):
        return False


def build_typescript_index(root: Path, sources: dict[str, str] | None = None) -> RepositoryIndex:
    root = root.resolve()
    if shutil.which("node") is None:
        raise ValueError("Node.js 20+ is required for TypeScript analysis")
    compiler = compiler_path()
    files = (
        source_files(root)
        if sources is None
        else sorted(name for name in sources if Path(name).suffix in EXTENSIONS)
    )
    texts = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if sources is None
        else hashlib.sha256(sources[name].encode()).hexdigest()
        for name in files
    }
    bridge = Path(__file__).with_name("ts_bridge.cjs")
    request = {"root": str(root), "files": files, "sources": sources}
    own = {str(root / name) for name in files}
    if sources is not None:
        texts.update(
            {
                name: hashlib.sha256(text.encode()).hexdigest()
                for name, text in sources.items()
                if name.endswith(".json")
            }
        )
        own.update(str(root / name) for name in sources)
    with IndexCache(root, str(bridge)) as cache:
        key = cache.key(
            "typescript-project",
            str(compiler),
            json.dumps([texts, hashlib.sha256(compiler.read_bytes()).hexdigest()], sort_keys=True),
        )
        payload = cache.get_data(key)
        reused = isinstance(payload, dict) and _valid_inputs(payload, own)
        if not reused:
            environment = {**os.environ, "CHANGE_IMPACT_TYPESCRIPT_PATH": str(compiler)}
            try:
                result = subprocess.run(
                    ["node", "--max-old-space-size=2048", str(bridge)],
                    input=json.dumps(request),
                    cwd=root,
                    capture_output=True,
                    text=True,
                    env=environment,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise ValueError("TypeScript analysis exceeded the 120-second time limit") from None
            if result.returncode:
                raise ValueError(
                    result.stderr.strip()[:2000] or "TypeScript compiler analysis failed"
                )
            payload = json.loads(result.stdout)
            cache.put_data(key, payload)
        status = cache.status
    index = RepositoryIndex()
    index.language = "typescript"
    for item in payload["modules"]:
        module = Module(item["name"], item["file"], ast.Module(body=[], type_ignores=[]))
        module.language = "typescript"
        module.symbols = [Symbol(**symbol) for symbol in item["symbols"]]
        module.scopes = {"": Scope(None, "module")}
        module.import_evidence = item["imports"]
        module.content_hash, module.ast_hash, module.binding_hash = (
            item["content_hash"],
            item["ast_hash"],
            item["binding_hash"],
        )
        index[module.name] = module
    symbols = {symbol.id: symbol for module in index.values() for symbol in module.symbols}
    index._memo["relationships"] = (
        symbols,
        [Edge(**edge) for edge in payload["edges"]],
        payload["unresolved"],
    )
    index._memo["routes"] = (payload["routes"], payload["diagnostics"])
    index.typescript_tests = payload["tests"]
    index.diagnostics = payload["diagnostics"]
    index.stats = {
        "parsed_files": 0 if reused else len(files),
        "cache_hits": len(files) if reused else 0,
        "project_cache_hit": reused,
        "cache_status": status,
        "compiler_version": payload["compiler_version"],
        "graph_builds": 1,
        "route_builds": 1,
    }
    return index


def find_related_typescript_tests(index, query: str, depth: int = 8) -> list[dict]:
    from dataclasses import asdict

    from .related import _path_matches, discover_routes
    from .trace import relationships, select_symbol, trace_callers

    symbols, edges, _ = relationships(index)
    target = select_symbol(symbols, query)
    trace = trace_callers(index, target.id, depth)
    reachable = {target.id, *(path[0]["caller"] for path in trace["paths"])}
    routes = [route for route in discover_routes(index) if route["symbol"] in reachable]
    results = []
    for test in index.typescript_tests:
        calls = [
            edge for edge in edges if edge.caller == test["symbol"] and edge.target in reachable
        ]
        endpoints = [
            {
                "file": call["file"],
                "line": call["line"],
                "method": call["method"],
                "path": call["path"],
                "route_file": route["file"],
                "route_line": route["line"],
                "reason": "http_path_candidate",
            }
            for call in test["http_calls"]
            for route in routes
            if route["method"] in {call["method"], "ANY"}
            and _path_matches(route["path"], call["path"])
        ]
        if calls or endpoints:
            results.append(
                {
                    "test": asdict(symbols[test["symbol"]]),
                    "title": test["title"],
                    "direct_calls": [asdict(edge) for edge in calls],
                    "endpoint_calls": endpoints,
                    "fixture_dependencies": [],
                    "confidence": "static" if calls else "candidate",
                }
            )
    return results
