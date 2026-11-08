"""MCP tools for coding agents. Install with the `mcp` extra."""

from __future__ import annotations

from pathlib import Path


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "Install the MCP extra: pip install 'change-impact-investigator[mcp]'"
        ) from exc

    from .ai import summarize_impact
    from .baseline import compare_impact, create_impact_baseline
    from .impact import inspect_change_impact
    from .index import index_repository
    from .related import find_related_tests
    from .repository import load_index
    from .trace import trace_callers

    server = FastMCP("Change Impact Investigator")

    @server.tool(name="index_repository")
    def index_repository_tool(repo: str, language: str = "python") -> dict:
        """Update the persistent source index and report parsed/reused file counts."""
        return index_repository(Path(repo), language)

    @server.tool(name="trace_callers")
    def trace_callers_tool(
        repo: str, symbol: str, depth: int = 3, language: str = "python"
    ) -> dict:
        """Trace Python callers of a symbol with file and line evidence."""
        return trace_callers(load_index(Path(repo), language), symbol, depth)

    @server.tool(name="find_related_tests")
    def find_related_tests_tool(
        repo: str, symbol: str, depth: int = 8, language: str = "python"
    ) -> list[dict]:
        """Find pytest tests linked by calls, fixtures, or affected HTTP path candidates."""
        return find_related_tests(load_index(Path(repo), language), symbol, depth)

    @server.tool(name="inspect_change_impact")
    def inspect_change_impact_tool(
        repo: str, symbol: str | None = None, base: str = "HEAD", depth: int = 8
    ) -> dict:
        """Inspect Python working tree changes against a Git base and report source evidence."""
        return inspect_change_impact(Path(repo), symbol, base, depth)

    @server.tool(name="create_impact_baseline")
    def create_baseline_tool(repo: str, symbol: str) -> dict:
        """Save current evidence before editing a symbol."""
        return create_impact_baseline(Path(repo), symbol)

    @server.tool(name="compare_impact")
    def compare_impact_tool(repo: str, baseline_id: str) -> dict:
        """Compare current connections against a saved baseline."""
        return compare_impact(Path(repo), baseline_id)

    @server.tool(name="summarize_impact")
    def summarize_impact_tool(
        repo: str, provider: str, symbol: str | None = None, model: str | None = None
    ) -> dict:
        """Generate an optional summary. ollama uses local AI. openai sends report data online."""
        return summarize_impact(inspect_change_impact(Path(repo), symbol), provider, model)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
