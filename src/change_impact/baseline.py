"""Save and compare impact evidence before and after an edit."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .git import repository_root
from .impact import inspect_change_impact
from .repository import load_index
from .trace import relationships


def _cache(root: Path) -> Path:
    cache = root.resolve() / ".impact-cache"
    if cache.is_symlink():
        raise ValueError("Baseline cache must be a directory inside the repository")
    return cache


def create_impact_baseline(root: Path, symbol: str, language: str = "python") -> dict:
    root = repository_root(root)
    report = inspect_change_impact(root, symbol, language=language)
    baseline_id = uuid.uuid4().hex
    cache = _cache(root)
    cache.mkdir(exist_ok=True)
    path = cache / f"{baseline_id}.json"
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    return {"baseline_id": baseline_id, "symbol": report["impacts"][0]["symbol"], "file": str(path)}


def _connections(report: dict) -> dict[str, dict[tuple, dict]]:
    if len(report["impacts"]) != 1:
        raise ValueError("Comparison requires one selected symbol")
    impact = report["impacts"][0]
    return {
        "callers": {
            (edge["caller"], edge["target"], edge["expression"]): edge
            for path in impact["caller_paths"]
            for edge in path
        },
        "routes": {
            (route["method"], route["path"], route["symbol"]): route
            for route in impact["affected_routes"]
        },
        "tests": {
            (item["test"]["module"], item["test"]["qualname"]): item
            for item in impact["related_tests"]
        },
        "imports": {
            (item["file"], item["scope"] or "", item["alias"], item["target"]): item
            for item in impact.get("imports", [])
        },
        "dynamic_calls": {
            (item["file"], item["caller"] or "", item["expression"]): item
            for item in report["unresolved_dynamic_calls"]
        },
    }


def compare_impact(root: Path, baseline_id: str) -> dict:
    root = repository_root(root)
    if not (len(baseline_id) == 32 and all(c in "0123456789abcdef" for c in baseline_id)):
        raise ValueError("Invalid baseline ID")
    path = _cache(root) / f"{baseline_id}.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    if before["repository"] != str(root):
        raise ValueError("Baseline belongs to another repository")
    symbol = before["impacts"][0]["symbol"]
    symbol_id = f"{symbol['module']}:{symbol['qualname']}"
    language = before.get("language", "python")
    index = load_index(root, language)
    symbols, _, _ = relationships(index)
    removed = symbol_id not in symbols
    failed_files = {item["file"] for item in index.diagnostics}
    failed_files.update(item["other_file"] for item in index.diagnostics if item.get("other_file"))
    if removed and symbol["file"] in failed_files:
        raise ValueError(f"Cannot compare symbol because {symbol['file']} could not be indexed")
    current = inspect_change_impact(root, None if removed else symbol_id, language=language)
    if removed:
        current["impacts"] = [
            {"symbol": symbol, "caller_paths": [], "affected_routes": [], "related_tests": []}
        ]
    older, newer = _connections(before), _connections(current)
    changes = {
        name: {
            "added": [newer[name][key] for key in sorted(newer[name].keys() - older[name].keys())],
            "removed": [
                older[name][key] for key in sorted(older[name].keys() - newer[name].keys())
            ],
        }
        for name in older
    }
    current_symbol = current["impacts"][0]["symbol"]
    old_fingerprint = symbol.get("fingerprint")
    new_fingerprint = current_symbol.get("fingerprint")
    old_file_hash = before.get("source_hashes", {}).get(symbol["file"])
    new_file_hash = current.get("source_hashes", {}).get(current_symbol["file"])
    return {
        "baseline_id": baseline_id,
        "symbol": current["impacts"][0]["symbol"],
        "symbol_removed": removed,
        "symbol_source_changed": True
        if removed
        else (old_fingerprint != new_fingerprint if old_fingerprint and new_fingerprint else None),
        "source_file_changed": True
        if removed
        else (old_file_hash != new_file_hash if old_file_hash and new_file_hash else None),
        "location_changed": (symbol["file"], symbol["line"])
        != (current_symbol["file"], current_symbol["line"]),
        "changes": changes,
        "current": current,
    }
