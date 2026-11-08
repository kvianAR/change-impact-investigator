"""MCP tools for coding agents. Install with the `mcp` extra."""

from __future__ import annotations

from pathlib import Path


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("Install the MCP extra: pip install 'change-impact-investigator[mcp]'") from exc

    from .impact import inspect_change_impact
    from .index import build_index
    from .related import find_related_tests
    from .trace import trace_callers

    server = FastMCP("Change Impact Investigator")

    @server.tool(name="trace_callers")
    def trace_callers_tool(repo: str, symbol: str, depth: int = 3) -> dict:
        """Trace Python callers of a symbol with file and line evidence."""
        return trace_callers(build_index(Path(repo)), symbol, depth)

    @server.tool(name="find_related_tests")
    def find_related_tests_tool(repo: str, symbol: str) -> list[dict]:
        """Find pytest tests linked to a symbol or an affected FastAPI route."""
        return find_related_tests(build_index(Path(repo)), symbol)

    @server.tool(name="inspect_change_impact")
    def inspect_change_impact_tool(repo: str, symbol: str | None = None) -> dict:
        """Inspect uncommitted Python changes against HEAD and report affected paths."""
        return inspect_change_impact(Path(repo), symbol)

    return server


def main() -> None:
    create_server().run(transport="stdio")
