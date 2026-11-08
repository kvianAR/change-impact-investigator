"""Command-line interface for local investigations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .impact import inspect_change_impact
from .ai import summarize_impact
from .baseline import compare_impact, create_impact_baseline
from .index import build_index
from .related import find_related_tests
from .trace import trace_callers


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate Python change impact with source evidence")
    parser.add_argument("command", choices=["trace-callers", "related-tests", "inspect-change-impact", "baseline", "compare", "summarize"])
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--symbol")
    parser.add_argument("--baseline-id")
    parser.add_argument("--provider", choices=["ollama", "openai"])
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.command in {"trace-callers", "related-tests", "baseline"} and not args.symbol:
        parser.error("--symbol is required for this command")
    if args.command == "compare" and not args.baseline_id:
        parser.error("--baseline-id is required for comparison")
    if args.command == "summarize" and not args.provider:
        parser.error("--provider is required for an AI summary")
    if args.command == "trace-callers":
        result = trace_callers(build_index(args.repo), args.symbol)
    elif args.command == "related-tests":
        result = find_related_tests(build_index(args.repo), args.symbol)
    elif args.command == "baseline":
        result = create_impact_baseline(args.repo, args.symbol)
    elif args.command == "compare":
        result = compare_impact(args.repo, args.baseline_id)
    elif args.command == "summarize":
        result = summarize_impact(inspect_change_impact(args.repo, args.symbol), args.provider, args.model)
    else:
        result = inspect_change_impact(args.repo, args.symbol)
    print(json.dumps(result, indent=2))
