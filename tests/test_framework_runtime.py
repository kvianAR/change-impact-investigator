import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from change_impact.index import build_index
from change_impact.related import discover_routes
from change_impact.trace import trace_callers


def test_flask_blueprint_evidence_matches_live_requests(tmp_path: Path) -> None:
    pytest.importorskip("flask")
    source = tmp_path / "app.py"
    source.write_text(
        "from flask import Flask,Blueprint\nbp=Blueprint('orders',__name__,url_prefix='/v1')\ndef validate(q): return 1<=q<=100\n@bp.get('/orders/<int:quantity>')\ndef orders(quantity): return ('ok',200) if validate(quantity) else ('invalid',400)\ndef create_app():\n    app=Flask(__name__)\n    app.register_blueprint(bp,url_prefix='/api')\n    return app\n"
    )
    specification = importlib.util.spec_from_file_location("authored_flask_app", source)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    client = module.create_app().test_client()
    assert client.get("/api/orders/10").status_code == 200
    assert client.get("/api/orders/0").status_code == 400
    index = build_index(tmp_path)
    assert discover_routes(index)[0]["path"] == "/api/orders/<int:quantity>"
    assert trace_callers(index, "app:validate")["paths"][0][0]["caller"] == "app:orders"


def test_django_include_evidence_matches_live_class_view(tmp_path: Path) -> None:
    pytest.importorskip("django")
    (tmp_path / "settings.py").write_text("ROOT_URLCONF='urls'\n")
    (tmp_path / "urls.py").write_text(
        "from django.urls import path,include\nurlpatterns=[path('api/',include('orders_urls'))]\n"
    )
    (tmp_path / "orders_urls.py").write_text(
        "from django.urls import path\nfrom views import Orders\nurlpatterns=[path('orders/<int:quantity>/',Orders.as_view())]\n"
    )
    (tmp_path / "views.py").write_text(
        "from django.views import View\nfrom django.http import HttpResponse\ndef validate(q): return 1<=q<=100\nclass Orders(View):\n    def get(self,request,quantity): return HttpResponse(status=200 if validate(quantity) else 400)\n"
    )
    code = "from django.conf import settings; settings.configure(ROOT_URLCONF='urls',SECRET_KEY='test-only',ALLOWED_HOSTS=['testserver']); import django; django.setup(); from django.test import Client; client=Client(); assert client.get('/api/orders/10/').status_code==200; assert client.get('/api/orders/0/').status_code==400"
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        check=True,
        capture_output=True,
        timeout=20,
    )
    index = build_index(tmp_path)
    route = discover_routes(index)[0]
    assert route["path"] == "/api/orders/<int:quantity>/"
    assert route["symbol"] == "views:Orders.get"
    assert trace_callers(index, "views:validate")["paths"][0][0]["caller"] == "views:Orders.get"
