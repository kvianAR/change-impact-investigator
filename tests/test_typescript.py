import os
import shutil
import subprocess
from pathlib import Path

import pytest

from change_impact.baseline import compare_impact, create_impact_baseline
from change_impact.impact import inspect_change_impact
from change_impact.related import discover_routes, find_related_tests
from change_impact.repository import load_index
from change_impact.trace import trace_callers
from change_impact.typescript import build_typescript_index, compiler_path

try:
    compiler_path()
    if shutil.which("node") is None:
        raise ValueError("Node.js unavailable")
except ValueError:
    if os.environ.get("CHANGE_IMPACT_REQUIRE_TYPESCRIPT") == "1":
        raise
    pytest.skip("Optional TypeScript runtime is not installed", allow_module_level=True)


def test_compiler_resolves_import_aliases_and_transitive_calls(tmp_path: Path) -> None:
    (tmp_path / "v.ts").write_text(
        "export function validate(value: string) { return value.length > 0; }\n"
    )
    (tmp_path / "api.ts").write_text(
        "import {validate as check} from './v';\nexport function save() { return check('x'); }\nexport function route() { return save(); }\n"
    )
    result = trace_callers(build_typescript_index(tmp_path), "v.ts:validate")
    assert [path[0]["caller"] for path in result["paths"]] == ["api.ts:save", "api.ts:route"]
    assert result["imports"][0]["alias"] == "check"
    assert build_typescript_index(tmp_path).stats["project_cache_hit"]


def test_checker_resolves_inherited_methods_and_flags_dynamic_dispatch(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text(
        "class Base { check() { return true; } }\nclass Child extends Base {}\nfunction run(value: Child) { return value.check(); }\nfunction dynamic(registry: any, name: string) { return registry[name](); }\n"
    )
    result = trace_callers(build_typescript_index(tmp_path), "a.ts:Base.check")
    assert result["paths"][0][0]["caller"] == "a.ts:run"
    assert any(
        item["expression"] == "registry[name]" for item in result["unresolved_dynamic_calls"]
    )


def test_express_mounts_and_jest_callback_metadata(tmp_path: Path) -> None:
    (tmp_path / "v.ts").write_text("export function validate() { return true; }\n")
    (tmp_path / "api.ts").write_text(
        "import express, {Router} from 'express';\nimport {validate} from './v';\nconst app=express(); const router=Router();\nfunction orders() { return validate(); }\nrouter.post('/orders',orders); app.use('/api',router);\n"
    )
    (tmp_path / "v.test.ts").write_text(
        "import {validate} from './v';\ntest('validates', () => { validate(); });\n"
    )
    index = build_typescript_index(tmp_path)
    assert discover_routes(index)[0]["path"] == "/api/orders"
    assert index.typescript_tests[0]["title"] == "validates"
    assert any(
        "test validates" in path[0]["caller"]
        for path in trace_callers(index, "v.ts:validate")["paths"]
    )


def test_typescript_test_links_and_mixed_repository(tmp_path: Path) -> None:
    (tmp_path / "v.ts").write_text("export const validate = () => true;\n")
    (tmp_path / "v.test.ts").write_text(
        "import {validate} from './v';\nit('validates',()=>{validate();});\n"
    )
    (tmp_path / "legacy.py").write_text("def validate(): return True\n")
    index = load_index(tmp_path, "auto")
    assert index.language == "mixed"
    assert find_related_tests(index, "v.ts:validate")[0]["title"] == "validates"
    assert trace_callers(index, "legacy:validate")["paths"] == []


def commit_sources(root: Path) -> None:
    for arguments in [
        ["init"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "baseline",
        ],
    ]:
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_typescript_git_impact_baseline_and_deleted_source(tmp_path: Path) -> None:
    (tmp_path / "v.ts").write_text("export function validate() { return 1; }\n")
    (tmp_path / "api.ts").write_text(
        "import express from 'express'; import {validate} from './v';\nconst app=express(); function route() {return validate();}\napp.post('/orders',route);\n"
    )
    (tmp_path / "v.test.ts").write_text(
        "import {validate} from './v'; test('validates',()=>{validate();});\n"
    )
    commit_sources(tmp_path)
    baseline = create_impact_baseline(tmp_path, "v.ts:validate", "typescript")
    (tmp_path / "v.ts").write_text("export function validate() { return 2; }\n")
    report = inspect_change_impact(tmp_path, language="typescript")
    assert report["changed_files"] == ["v.ts"]
    assert report["impacts"][0]["affected_routes"][0]["path"] == "/orders"
    assert report["impacts"][0]["related_tests"][0]["title"] == "validates"
    assert compare_impact(tmp_path, baseline["baseline_id"])["symbol_source_changed"]
    (tmp_path / "v.ts").unlink()
    deleted = inspect_change_impact(tmp_path, language="typescript")
    assert deleted["impacts"][0]["reason"] == "removed_symbol"
    assert deleted["impacts"][0]["evidence_state"] == "base"


def test_historical_tsconfig_paths_and_configuration_impact(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("export function check() {return 1;}\n")
    (tmp_path / "b.ts").write_text("export function check() {return 2;}\n")
    (tmp_path / "caller.ts").write_text(
        "import {check} from '@validator'; export function run(){return check();}\n"
    )
    config = tmp_path / "tsconfig.json"
    config.write_text('{"compilerOptions":{"baseUrl":".","paths":{"@validator":["./a"]}}}')
    commit_sources(tmp_path)
    baseline = create_impact_baseline(tmp_path, "a.ts:check", "typescript")
    config.write_text('{"compilerOptions":{"baseUrl":".","paths":{"@validator":["./b"]}}}')
    report = inspect_change_impact(tmp_path, language="typescript")
    assert report["configuration_changes"] == ["tsconfig.json"]
    assert report["impacts"]
    comparison = compare_impact(tmp_path, baseline["baseline_id"])
    assert comparison["changes"]["callers"]["removed"][0]["caller"] == "caller.ts:run"
    (tmp_path / "a.ts").unlink()
    removed = next(
        item
        for item in inspect_change_impact(tmp_path, language="typescript")["impacts"]
        if item["symbol"]["module"] == "a.ts"
    )
    assert removed["caller_paths"][0][0]["caller"] == "caller.ts:run"


def test_typescript_parse_failure_preserves_historical_evidence(tmp_path: Path) -> None:
    path = tmp_path / "a.ts"
    path.write_text("export function check() {return 1;}\n")
    commit_sources(tmp_path)
    path.write_text("export function check(\n")
    report = inspect_change_impact(tmp_path, language="typescript")
    assert report["impacts"][0]["reason"] == "current_source_unparseable"
