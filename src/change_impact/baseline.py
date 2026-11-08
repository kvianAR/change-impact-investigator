"""Save and compare impact evidence before and after an edit."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .impact import inspect_change_impact
from .index import build_index
from .trace import relationships


def _cache(root: Path) -> Path:
    return root.resolve() / ".impact-cache"


def create_impact_baseline(root: Path, symbol: str) -> dict:
    root = root.resolve()
    report = inspect_change_impact(root, symbol)
    baseline_id = uuid.uuid4().hex
    cache = _cache(root)
    cache.mkdir(exist_ok=True)
    path = cache / f"{baseline_id}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"baseline_id": baseline_id, "symbol": report["impacts"][0]["symbol"], "file": str(path)}


def _connections(report: dict) -> dict[str, dict[tuple, dict]]:
    if len(report["impacts"]) != 1:
        raise ValueError("Comparison requires one selected symbol")
    impact = report["impacts"][0]
    return {
        "callers": {(edge["caller"], edge["target"], edge["expression"]): edge for path in impact["caller_paths"] for edge in path},
        "routes": {(route["method"], route["path"], route["symbol"]): route for route in impact["affected_routes"]},
        "tests": {(item["test"]["module"], item["test"]["qualname"]): item for item in impact["related_tests"]},
        "dynamic_calls": {(item["file"], item["caller"] or "", item["expression"]): item for item in report["unresolved_dynamic_calls"]},
    }


def compare_impact(root: Path, baseline_id: str) -> dict:
    root = root.resolve()
    if not (len(baseline_id) == 32 and all(c in "0123456789abcdef" for c in baseline_id)):
        raise ValueError("Invalid baseline ID")
    path = _cache(root) / f"{baseline_id}.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    if before["repository"] != str(root):
        raise ValueError("Baseline belongs to another repository")
    symbol = before["impacts"][0]["symbol"]
    symbol_id = f"{symbol['module']}:{symbol['qualname']}"
    symbols, _, _ = relationships(build_index(root))
    removed = symbol_id not in symbols
    current = inspect_change_impact(root, None if removed else symbol_id)
    if removed:
        current["impacts"] = [{"symbol": symbol, "caller_paths": [], "affected_routes": [], "related_tests": []}]
    older, newer = _connections(before), _connections(current)
    changes = {
        name: {
            "added": [newer[name][key] for key in sorted(newer[name].keys() - older[name].keys())],
            "removed": [older[name][key] for key in sorted(older[name].keys() - newer[name].keys())],
        }
        for name in older
    }
    return {"baseline_id": baseline_id, "symbol": current["impacts"][0]["symbol"], "symbol_removed": removed, "changes": changes, "current": current}
