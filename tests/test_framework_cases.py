from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_route_map, find_related_tests


def test_nested_router_mounts_aliases_and_trailing_slash(tmp_path: Path) -> None:
    (tmp_path / "routes.py").write_text(
        "from fastapi import APIRouter as Router\n"
        "router = Router(prefix='/orders')\n"
        "@router.get('/{order_id}/')\ndef get_order(order_id): pass\n"
    )
    (tmp_path / "main.py").write_text(
        "import fastapi as web\nfrom routes import router\n"
        "app = web.FastAPI()\ngroup = web.APIRouter(prefix='/v1')\n"
        "group.include_router(router, prefix='/store')\n"
        "app.include_router(group, prefix='/api')\n"
    )
    routes, diagnostics = discover_route_map(build_index(tmp_path))
    assert diagnostics == []
    assert routes[0]["path"] == "/api/v1/store/orders/{order_id}/"
    assert len(routes[0]["mount_evidence"]) == 2


def test_unmounted_router_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/hidden')\ndef hidden(): pass\n"
    )
    routes, diagnostics = discover_route_map(build_index(tmp_path))
    assert routes == []
    assert diagnostics[0]["reason"] == "unmounted_router"


def test_dynamic_prefix_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import FastAPI, APIRouter\napp=FastAPI()\nrouter=APIRouter()\napp.include_router(router,prefix=PREFIX)\n@router.get('/orders')\ndef orders(): pass\n"
    )
    routes, diagnostics = discover_route_map(build_index(tmp_path))
    assert routes == []
    assert "unresolved_router_mount" in {item["reason"] for item in diagnostics}


def test_parameterized_endpoint_request_is_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import FastAPI\napp=FastAPI()\ndef check(): pass\n@app.get('/orders/{order_id}')\ndef route(order_id):\n    check()\n"
    )
    (tmp_path / "orders_test.py").write_text(
        "def test_route(client):\n    client.request('GET','/orders/123?verbose=1')\n"
    )
    tests = find_related_tests(build_index(tmp_path), "a:check")
    assert tests[0]["confidence"] == "candidate"
    assert tests[0]["endpoint_calls"][0]["route_line"] == 4


def test_transitive_conftest_fixture_links(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(): return True\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text(
        "import pytest\nfrom v import check\n"
        "@pytest.fixture\ndef validated():\n    return check()\n"
        "@pytest.fixture\ndef client(validated):\n    return validated\n"
    )
    (tests / "test_order.py").write_text("def test_order(client):\n    assert client\n")
    result = find_related_tests(build_index(tmp_path), "v:check")
    assert result[0]["test"]["qualname"] == "test_order"
    assert [item["name"] for item in result[0]["fixture_dependencies"][0]["path"]] == [
        "client",
        "validated",
    ]


def test_autouse_and_usefixtures_markers(tmp_path: Path) -> None:
    (tmp_path / "v.py").write_text("def check(): return True\n")
    (tmp_path / "test_order.py").write_text(
        "import pytest\nfrom v import check\n"
        "@pytest.fixture(autouse=True)\ndef validated():\n    check()\n"
        "@pytest.mark.usefixtures('validated')\ndef test_order():\n    pass\n"
    )
    result = find_related_tests(build_index(tmp_path), "v:check")
    assert result[0]["fixture_dependencies"][0]["reason"] == "autouse_fixture"


def test_reassigned_router_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/old')\ndef old(): pass\napp=FastAPI()\n"
    )
    routes, diagnostics = discover_route_map(build_index(tmp_path))
    assert routes == []
    assert "reassigned_router_variable" in {item["reason"] for item in diagnostics}
