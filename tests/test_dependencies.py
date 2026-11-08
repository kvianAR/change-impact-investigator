from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_routes
from change_impact.trace import trace_callers


def test_parameter_annotated_and_router_dependencies(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import FastAPI, Depends, APIRouter\nfrom typing import Annotated\ndef check(): pass\napp=FastAPI(dependencies=[Depends(check)])\nrouter=APIRouter()\n@router.get('/orders')\ndef orders(value: Annotated[str, Depends(check)]): pass\napp.include_router(router)\n"
    )
    index = build_index(tmp_path)
    result = trace_callers(index, "a:check")
    assert {path[0]["caller"] for path in result["paths"]} == {"a:orders"}
    assert all(path[0]["resolution"] == "dependency_injection" for path in result["paths"])
    assert discover_routes(index)[0]["path"] == "/orders"


def test_returned_application_factory_routes(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import FastAPI, Depends\ndef check(): pass\ndef create_app():\n    app=FastAPI()\n    @app.get('/orders')\n    def orders(value=Depends(check)): pass\n    return app\n"
    )
    index = build_index(tmp_path)
    route = discover_routes(index)[0]
    assert route["symbol"] == "a:create_app.orders"
    assert route["factory"] == "a:create_app"
    assert trace_callers(index, "a:check")["paths"][0][0]["caller"] == "a:create_app.orders"


def test_dynamic_dependency_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import Depends\ndef check(): pass\ndef route(value=Depends(factory())): pass\n"
    )
    result = trace_callers(build_index(tmp_path), "a:check")
    assert any(
        item["reason"] == "dynamic_or_annotation_only_dependency_provider"
        for item in result["unresolved_dynamic_calls"]
    )
