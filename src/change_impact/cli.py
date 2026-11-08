"""Command-line interface for local investigations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .impact import inspect_change_impact
from .index import build_index
from .related import find_related_tests
from .trace import trace_callers


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate Python change impact with source evidence")
    parser.add_argument("command", choices=["trace-callers", "related-tests", "inspect-change-impact"])
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--symbol")
    args = parser.parse_args()
    if args.command != "inspect-change-impact" and not args.symbol:
        parser.error("--symbol is required for this command")
    if args.command == "trace-callers":
        result = trace_callers(build_index(args.repo), args.symbol)
    elif args.command == "related-tests":
        result = find_related_tests(build_index(args.repo), args.symbol)
    else:
        result = inspect_change_impact(args.repo, args.symbol)
    print(json.dumps(result, indent=2))
