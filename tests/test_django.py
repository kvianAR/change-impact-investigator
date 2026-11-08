from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_routes, find_related_tests
from change_impact.trace import trace_callers


def test_urlconf_include_and_function_view(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text("ROOT_URLCONF='urls'\n")
    (tmp_path / "urls.py").write_text(
        "from django.urls import path,include\nurlpatterns=[path('api/',include('orders_urls'))]\n"
    )
    (tmp_path / "orders_urls.py").write_text(
        "from django.urls import path\nfrom views import orders\nurlpatterns=[path('orders/<int:order_id>/',orders)]\n"
    )
    (tmp_path / "views.py").write_text("def check(): pass\ndef orders(request,order_id): check()\n")
    (tmp_path / "test_orders.py").write_text(
        "def test_order(client): client.get('/api/orders/12/')\n"
    )
    index = build_index(tmp_path)
    route = discover_routes(index)[0]
    assert route["path"] == "/api/orders/<int:order_id>/"
    assert route["root_resolution"] == "settings"
    assert find_related_tests(index, "views:check")[0]["test"]["qualname"] == "test_order"


def test_class_view_http_dispatch_edges(tmp_path: Path) -> None:
    (tmp_path / "urls.py").write_text(
        "from django.urls import path\nfrom views import Orders\nurlpatterns=[path('orders/',Orders.as_view())]\n"
    )
    (tmp_path / "views.py").write_text(
        "from django.views import View\ndef check(): pass\nclass Orders(View):\n    def dispatch(self,request): return super().dispatch(request)\n    def get(self,request): return check()\n"
    )
    index = build_index(tmp_path)
    route = discover_routes(index)[0]
    assert route["method"] == "GET"
    assert route["symbol"] == "views:Orders.dispatch"
    assert any(
        path[0]["resolution"] == "framework_dispatch"
        for path in trace_callers(index, "views:check")["paths"]
    )
