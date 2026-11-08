import json
from pathlib import Path

import pytest

from change_impact.models import ModelStore, SettingsConflict


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def available(self):
        return True

    def get(self, provider):
        return self.values.get(provider)

    def set(self, provider, value):
        self.values[provider] = value

    def delete(self, provider):
        self.values.pop(provider, None)


def test_save_activate_edit_and_reload_without_exposing_keys(tmp_path: Path) -> None:
    credentials = MemoryCredentials()
    store = ModelStore(tmp_path, credentials)
    state = store.save_model(
        {
            "provider": "openrouter",
            "model": "vendor/my-model",
            "name": "My model",
            "api_key": "test-private-key",
            "activate": True,
        }
    )
    profile = state["models"][0]
    assert state["active_model_id"] == profile["id"]
    assert "test-private-key" not in json.dumps(state)
    assert "test-private-key" not in store.path.read_text()
    assert "test-private-key" not in repr(store.connection())
    reloaded = ModelStore(tmp_path, credentials)
    assert reloaded.connection().model == "vendor/my-model"
    reloaded.save_model({**profile, "model": "vendor/updated-model"}, state["revision"])
    assert reloaded.connection().model == "vendor/updated-model"
    reloaded.delete(profile["id"])
    assert reloaded.state()["active_model_id"] is None


def test_revision_conflicts_do_not_overwrite_state(tmp_path: Path) -> None:
    store = ModelStore(tmp_path, MemoryCredentials())
    store.save_model({"provider": "ollama", "model": "local-a"}, 0)
    with pytest.raises(SettingsConflict):
        store.save_model({"provider": "ollama", "model": "local-b"}, 0)
    assert len(store.state()["models"]) == 1


def test_key_change_rolls_back_when_metadata_save_fails(tmp_path: Path, monkeypatch) -> None:
    credentials = MemoryCredentials()
    store = ModelStore(tmp_path, credentials)
    store.save_provider("openrouter", {"api_key": "old-test-key"})
    monkeypatch.setattr(store, "_write", lambda state: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        store.save_provider("openrouter", {"api_key": "new-test-key"})
    assert credentials.get("openrouter") == "old-test-key"


def test_active_model_requires_key_and_custom_endpoint_validation(tmp_path: Path) -> None:
    store = ModelStore(tmp_path, MemoryCredentials())
    with pytest.raises(ValueError, match="API key"):
        store.save_model({"provider": "openrouter", "model": "vendor/model", "activate": True})
    with pytest.raises(ValueError, match="HTTPS"):
        store.save_model(
            {"provider": "custom", "model": "model", "base_url": "http://remote.example/v1"}
        )
    assert store.state()["models"] == []
