import os
import shutil
from pathlib import Path

import pytest

from change_impact.related import discover_routes
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
