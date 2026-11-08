import io
import json
from unittest.mock import patch

from test_models import MemoryCredentials

from change_impact.ai import summarize_impact
from change_impact.models import ModelConnection, ModelStore
from change_impact.providers import model_catalog


def test_openrouter_uses_selected_model_and_chat_completion(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")
    response = io.BytesIO(b'{"choices":[{"message":{"content":"Impact summary"}}]}')
    with patch("change_impact.ai.urlopen", return_value=response) as transport:
        result = summarize_impact({}, "openrouter", "vendor/selected-model")
    request = transport.call_args.args[0]
    assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert json.loads(request.data)["model"] == "vendor/selected-model"
    assert result["summary"] == "Impact summary"
    assert "openrouter-test-key" not in json.dumps(result)


def test_active_model_is_used_without_explicit_provider(tmp_path) -> None:
    store = ModelStore(tmp_path, MemoryCredentials())
    store.save_model(
        {
            "provider": "openrouter",
            "model": "vendor/my-model",
            "api_key": "saved-test-key",
            "activate": True,
        }
    )
    with patch(
        "change_impact.ai.urlopen",
        return_value=io.BytesIO(b'{"choices":[{"message":{"content":"Summary"}}]}'),
    ):
        result = summarize_impact({}, store=store)
    assert result["model"] == "vendor/my-model"
    assert result["profile_id"] == store.state()["active_model_id"]


def test_openrouter_catalog_preserves_custom_model_ids() -> None:
    connection = ModelConnection("openrouter", "", "https://openrouter.ai/api/v1")
    response = io.BytesIO(
        b'{"data":[{"id":"vendor/new-model","name":"New model","context_length":128000}]}'
    )
    with patch("change_impact.providers.urlopen", return_value=response):
        result = model_catalog(connection)
    assert result == [{"id": "vendor/new-model", "name": "New model", "context_length": 128000}]
