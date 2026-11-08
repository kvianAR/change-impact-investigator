from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_routes, find_related_tests


def test_blueprint_prefix_override_and_related_endpoint_test(tmp_path: Path) -> None:
    (tmp_path / "views.py").write_text(
        "from flask import Blueprint\nbp=Blueprint('orders',__name__,url_prefix='/old')\ndef check(): pass\n@bp.route('/orders',methods=['POST'])\ndef orders(): check()\n"
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\nfrom views import bp\napp=Flask(__name__)\napp.register_blueprint(bp,url_prefix='/api')\n"
    )
    (tmp_path / "test_app.py").write_text(
        "def test_orders(client):\n    client.post('/api/orders')\n"
    )
    index = build_index(tmp_path)
    route = next(route for route in discover_routes(index) if route.get("framework") == "flask")
    assert route["path"] == "/api/orders"
    assert route["mount_evidence"][0]["file"] == "app.py"
    assert find_related_tests(index, "views:check")[0]["test"]["qualname"] == "test_orders"


def test_flask_factory_and_add_url_rule(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "from flask import Flask as App\ndef view(): pass\ndef create_app():\n    app=App(__name__)\n    app.add_url_rule('/orders',view_func=view,methods=['GET'])\n    return app\n"
    )
    routes = [
        route
        for route in discover_routes(build_index(tmp_path))
        if route.get("framework") == "flask"
    ]
    assert routes[0]["path"] == "/orders"
    assert routes[0]["factory"] == "app:create_app"
