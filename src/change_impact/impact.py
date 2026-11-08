"""Map an uncommitted Git diff to indexed Python symbols and call paths."""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict
from pathlib import Path

from .index import build_index
from .related import discover_routes, find_related_tests
from .trace import relationships, trace_callers


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(root: Path) -> dict[str, set[int]]:
    """Return added/modified lines in tracked files plus every line of untracked Python files."""
    proc = subprocess.run(
        ["git", "diff", "HEAD", "--unified=0", "--no-ext-diff", "--no-color", "--", "*.py"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    changed: dict[str, set[int]] = {}
    file: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            file = line[6:]
        elif file and (match := HUNK.match(line)):
            start, count = int(match.group(1)), int(match.group(2) or "1")
            changed.setdefault(file, set()).update(range(start, start + max(1, count)))
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "*.py"],
        cwd=root, capture_output=True, check=True,
    )
    for filename in filter(None, untracked.stdout.decode().split("\0")):
        path = root / filename
        changed[filename] = set(range(1, len(path.read_text(encoding="utf-8").splitlines()) + 1))
    return changed


def inspect_change_impact(root: Path, symbol: str | None = None) -> dict:
    root = root.resolve()
    index = build_index(root)
    symbols, _, unresolved = relationships(index)
    changes = changed_lines(root)
    targets = [symbols[symbol]] if symbol in symbols else []
    if symbol and not targets:
        from .trace import select_symbol
        targets = [select_symbol(symbols, symbol)]
    if not symbol:
        targets = [s for s in symbols.values() if any(s.line <= line <= s.end_line for line in changes.get(s.file, set()))]
        # A modified enclosing class should not duplicate its changed methods.
        targets = [s for s in targets if s.kind != "class"]
    routes = discover_routes(index)
    reports = []
    for target in targets:
        trace = trace_callers(index, target.id, depth=8)
        reachable = {target.id, *(path[0]["caller"] for path in trace["paths"])}
        reports.append({
            "symbol": asdict(target),
            "caller_paths": trace["paths"],
            "affected_routes": [route for route in routes if route["symbol"] in reachable],
            "related_tests": find_related_tests(index, target.id),
        })
    return {
        "repository": str(root), "base": "HEAD", "changed_files": sorted(changes),
        "impacts": reports, "unresolved_dynamic_calls": unresolved,
        "limits": ["Static analysis cannot resolve all runtime calls or prove behavioral impact."],
    }
