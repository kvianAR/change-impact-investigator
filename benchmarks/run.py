"""Check manually labeled callers at pinned revisions and measure index reuse."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
from pathlib import Path
from time import perf_counter

from change_impact import __version__
from change_impact.repository import load_index
from change_impact.trace import trace_callers


def run_case(case: dict, repositories: Path, reset_cache: bool = False) -> dict:
    checkout = repositories / case["directory"]
    actual_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True
    ).stdout.strip()
    if actual_revision != case["commit"]:
        raise ValueError(
            f"{case['name']} requires commit {case['commit']}, found {actual_revision}"
        )
    root = checkout / case["source_root"]
    cache = root / ".impact-cache/index.sqlite3"
    if reset_cache and cache.exists():
        if cache.is_symlink() or cache.parent.is_symlink():
            raise ValueError("Refusing to clear a cache through a symlink")
        with sqlite3.connect(cache) as database:
            database.execute("DELETE FROM source_index")
    started = perf_counter()
    initial = load_index(root, case["language"])
    initial_seconds = perf_counter() - started
    started = perf_counter()
    report = trace_callers(initial, case["symbol"], depth=1)
    query_seconds = perf_counter() - started
    started = perf_counter()
    warm = load_index(root, case["language"])
    warm_seconds = perf_counter() - started
    warm_report = trace_callers(warm, case["symbol"], depth=1)
    actual = {path[0]["caller"] for path in report["paths"]}
    expected = {item["caller"] for item in case["expected"]}
    true_positives = len(actual & expected)
    return {
        "name": case["name"],
        "repository": case["repository"],
        "commit": case["commit"],
        "language": case["language"],
        "symbol": case["symbol"],
        "modules": len(initial),
        "expected": case["expected"],
        "actual_edges": [path[0] for path in report["paths"]],
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
        "precision": true_positives / len(actual) if actual else 1.0,
        "recall": true_positives / len(expected) if expected else 1.0,
        "initial_index_seconds": round(initial_seconds, 4),
        "warm_index_seconds": round(warm_seconds, 4),
        "query_seconds": round(query_seconds, 4),
        "initial_stats": initial.stats,
        "warm_stats": warm.stats,
        "diagnostics": initial.diagnostics,
        "passed": actual == expected
        and report["paths"] == warm_report["paths"]
        and warm.stats["parsed_files"] == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="Clear only the analyzer's source-index table before measuring",
    )
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    results = [run_case(case, args.repos_dir.resolve(), args.reset_cache) for case in cases]
    report = {
        "tool_version": __version__,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "scope": "Nine manually labeled direct caller symbols across three pinned public repositories. These cases do not establish repository-wide precision or recall.",
        "cases": results,
        "passed": all(item["passed"] for item in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "report": str(args.output),
                "cases": [
                    {
                        "name": item["name"],
                        "precision": item["precision"],
                        "recall": item["recall"],
                        "missing": item["missing"],
                        "unexpected": item["unexpected"],
                        "warm_parsed_files": item["warm_stats"]["parsed_files"],
                    }
                    for item in results
                ],
            },
            indent=2,
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
