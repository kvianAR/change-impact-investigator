"""Command-line interface for local investigations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ai import summarize_impact
from .baseline import compare_impact, create_impact_baseline
from .impact import inspect_change_impact
from .index import index_repository
from .related import find_related_tests
from .repository import load_index
from .trace import trace_callers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate Python and TypeScript change impact with source evidence"
    )
    parser.add_argument(
        "command",
        choices=[
            "trace-callers",
            "related-tests",
            "inspect-change-impact",
            "baseline",
            "compare",
            "summarize",
            "index",
        ],
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--symbol")
    parser.add_argument("--baseline-id")
    parser.add_argument("--provider", choices=["ollama", "openai"])
    parser.add_argument("--model")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--language", choices=["python", "typescript", "auto"], default="python")
    args = parser.parse_args()
    if args.command in {"trace-callers", "related-tests", "baseline"} and not args.symbol:
        parser.error("--symbol is required for this command")
    if args.command == "compare" and not args.baseline_id:
        parser.error("--baseline-id is required for comparison")
    if args.command == "summarize" and not args.provider:
        parser.error("--provider is required for an AI summary")
    try:
        if args.command == "index":
            result = index_repository(args.repo, args.language)
        elif args.command == "trace-callers":
            result = trace_callers(load_index(args.repo, args.language), args.symbol, args.depth)
        elif args.command == "related-tests":
            result = find_related_tests(
                load_index(args.repo, args.language), args.symbol, args.depth
            )
        elif args.command == "baseline":
            result = create_impact_baseline(args.repo, args.symbol, args.language)
        elif args.command == "compare":
            result = compare_impact(args.repo, args.baseline_id)
        elif args.command == "summarize":
            result = summarize_impact(
                inspect_change_impact(args.repo, args.symbol, args.base, args.depth, args.language),
                args.provider,
                args.model,
            )
        else:
            result = inspect_change_impact(
                args.repo, args.symbol, args.base, args.depth, args.language
            )
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2))
