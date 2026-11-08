import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from examples.shop.api import app
from examples.shop.validators import validate_order


def test_valid_quantity() -> None:
    assert validate_order(100)


def test_invalid_quantity() -> None:
    assert not validate_order(0)


def test_create_order() -> None:
    client = TestClient(app)
    assert client.post("/orders", json={"quantity": 100}).status_code == 201


def test_preview_order() -> None:
    client = TestClient(app)
    assert client.post("/orders/preview", json={"quantity": 100}).status_code == 200
