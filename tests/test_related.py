from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_routes, find_related_tests


def test_fastapi_routes_and_related_tests(tmp_path: Path) -> None:
    (tmp_path / "validators.py").write_text("def validate(value):\n    return bool(value)\n")
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\nfrom validators import validate\n"
        "app = FastAPI()\n@app.post('/orders')\n"
        "def create_order(value):\n    return validate(value)\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_orders.py").write_text(
        "from validators import validate\n"
        "def test_validator():\n    assert validate('x')\n"
        "def test_endpoint(client):\n    assert client.post('/orders').status_code == 200\n"
    )
    index = build_index(tmp_path)
    assert [(r["method"], r["path"]) for r in discover_routes(index)] == [("POST", "/orders")]
    related = find_related_tests(index, "validators:validate")
    assert {
        item["test"]["name"] if "name" in item["test"] else item["test"]["qualname"]
        for item in related
    } == {"test_validator", "test_endpoint"}
