import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_models import MemoryCredentials

from change_impact.models import ModelStore
from change_impact.panel import ModelsPanel


@pytest.fixture
def panel(tmp_path):
    server = ModelsPanel(0, ModelStore(tmp_path, MemoryCredentials()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def request(panel, path, body=None, **headers):
    data = json.dumps(body).encode() if body is not None else None
    defaults = {"Content-Type": "application/json", "X-Impact-Token": panel.token, **headers}
    with urlopen(Request(panel.url + path, data=data, headers=defaults)) as response:
        return json.load(response)


def test_model_flow_preserves_one_active_model_without_returning_credentials(panel) -> None:
    state = request(panel, "/api/state")
    saved = request(
        panel,
        "/api/models",
        {
            "revision": state["revision"],
            "provider": "openrouter",
            "model": "vendor/model",
            "api_key": "test-private-key",
            "activate": True,
        },
    )
    assert "test-private-key" not in json.dumps(saved)
    assert saved["active_model_id"] == saved["models"][0]["id"]
    other = request(
        panel,
        "/api/models",
        {"revision": saved["revision"], "provider": "ollama", "model": "local-model"},
    )
    local_id = other["models"][1]["id"]
    active = request(panel, f"/api/models/{local_id}/activate", {"revision": other["revision"]})
    assert active["active_model_id"] == local_id


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Impact-Token": "invalid"},
        {"Origin": "https://attacker.example"},
        {"Host": "attacker.example"},
    ],
)
def test_api_rejects_other_sessions_origins_and_hosts(panel, headers) -> None:
    with pytest.raises(HTTPError) as error:
        request(panel, "/api/state", **headers)
    assert error.value.code == 403


def test_stale_updates_return_conflict(panel) -> None:
    request(panel, "/api/models", {"revision": 0, "provider": "ollama", "model": "first"})
    with pytest.raises(HTTPError) as error:
        request(panel, "/api/models", {"revision": 0, "provider": "ollama", "model": "second"})
    assert error.value.code == 409


def test_static_assets_and_session_bootstrap(panel) -> None:
    with urlopen(panel.url) as response:
        html = response.read().decode()
        assert panel.token in html
        assert "__PANEL_TOKEN__" not in html
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Cache-Control"] == "no-store"
    for path in ("/assets/app.js", "/assets/style.css", "/favicon.svg"):
        with urlopen(panel.url + path) as response:
            assert response.status == 200
            assert response.read()


def test_catalog_and_saved_model_test_use_selected_provider(panel, monkeypatch) -> None:
    connections = []

    def catalog(connection):
        connections.append(connection)
        return [{"id": "vendor/manual-model", "name": "Manual model", "context_length": None}]

    monkeypatch.setattr("change_impact.panel.model_catalog", catalog)
    response = request(panel, "/api/catalog", {"provider": "openrouter"})
    assert response["models"][0]["id"] == "vendor/manual-model"
    assert connections[0].base_url == "https://openrouter.ai/api/v1"
    saved = request(
        panel,
        "/api/models",
        {
            "revision": 0,
            "provider": "openrouter",
            "model": "vendor/manual-model",
            "api_key": "private-test-key",
            "max_output_tokens": 256,
        },
    )
    calls = []
    monkeypatch.setattr("change_impact.panel.generate_text", lambda *args: calls.append(args))
    profile_id = saved["models"][0]["id"]
    assert request(panel, f"/api/models/{profile_id}/test", {})["ok"] is True
    assert calls[0][0].api_key == "private-test-key"
    assert calls[0][0].model == "vendor/manual-model"
    assert calls[0][2] == 256


def test_provider_key_update_preserve_and_remove(panel) -> None:
    saved = request(panel, "/api/providers/openrouter", {"revision": 0, "api_key": "old-key"})
    updated = request(
        panel,
        "/api/providers/openrouter",
        {"revision": saved["revision"], "api_key": "updated-key"},
    )
    preserved = request(
        panel,
        "/api/providers/openrouter",
        {"revision": updated["revision"], "api_key": ""},
    )
    assert panel.store.credentials.get("openrouter") == "updated-key"
    removed = request(
        panel,
        "/api/providers/openrouter",
        {"revision": preserved["revision"], "remove_key": True},
    )
    assert panel.store.credentials.get("openrouter") is None
    assert not next(item for item in removed["providers"] if item["id"] == "openrouter")[
        "key_available"
    ]


def test_catalog_provider_failure_is_sanitized(panel, monkeypatch) -> None:
    def fail(connection):
        raise RuntimeError("Provider HTTP 401. Check the endpoint and API key.")

    monkeypatch.setattr("change_impact.panel.model_catalog", fail)
    with pytest.raises(HTTPError) as error:
        request(panel, "/api/catalog", {"provider": "openrouter", "api_key": "private-test-key"})
    assert error.value.code == 502
    assert "private-test-key" not in error.value.read().decode()
