import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

import change_impact

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_mcp_session_lists_and_calls_tools(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(): pass\ndef run():\n    check()\n")

    async def investigate() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from change_impact.server import main; main()"],
            env={"PYTHONPATH": str(Path(change_impact.__file__).parent.parent)},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                registered = await session.list_tools()
                assert {tool.name for tool in registered.tools} == {
                    "trace_callers",
                    "inspect_change_impact",
                    "find_related_tests",
                    "create_impact_baseline",
                    "compare_impact",
                    "summarize_impact",
                    "index_repository",
                }
                response = await session.call_tool(
                    "trace_callers", {"repo": str(tmp_path), "symbol": "v:check"}
                )
                assert not response.isError
                report = json.loads(response.content[0].text)
                assert report["paths"][0][0]["caller"] == "v:run"

    asyncio.run(asyncio.wait_for(investigate(), timeout=30))


def test_typescript_stdio_session_uses_the_selected_backend(tmp_path: Path) -> None:
    from change_impact.typescript import compiler_path

    try:
        compiler = compiler_path()
    except ValueError:
        if os.environ.get("CHANGE_IMPACT_REQUIRE_TYPESCRIPT") == "1":
            raise
        pytest.skip("TypeScript runtime unavailable")
    (tmp_path / "v.ts").write_text(
        "export function check(){return true;} export function run(){return check();}\n"
    )

    async def investigate() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "change_impact.server"],
            env={
                "PYTHONPATH": str(Path(change_impact.__file__).parent.parent),
                "CHANGE_IMPACT_TYPESCRIPT_PATH": str(compiler),
            },
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(
                    "trace_callers",
                    {"repo": str(tmp_path), "symbol": "v.ts:check", "language": "typescript"},
                )
                assert not response.isError
                assert json.loads(response.content[0].text)["paths"][0][0]["caller"] == "v.ts:run"

    asyncio.run(asyncio.wait_for(investigate(), timeout=30))
