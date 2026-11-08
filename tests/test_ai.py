import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from change_impact.ai import summarize_impact


def test_local_summary_uses_ollama_and_keeps_evidence() -> None:
    evidence = {"impacts": []}
    response = io.BytesIO(json.dumps({"response": "No impacted symbols found."}).encode())
    with patch("change_impact.ai.urlopen", return_value=response) as request:
        result = summarize_impact(evidence, "ollama")
    assert request.call_args.args[0].full_url == "http://127.0.0.1:11434/api/generate"
    assert result["evidence"] == evidence
    assert result["summary"] == "No impacted symbols found."


def test_online_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        summarize_impact({}, "openai")


def test_online_summary_parses_responses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    response = io.BytesIO(
        json.dumps({"output": [{"content": [{"type": "output_text", "text": "Summary"}]}]}).encode()
    )
    with patch("change_impact.ai.urlopen", return_value=response) as request:
        result = summarize_impact({}, "openai", "test-model")
    assert request.call_args.args[0].full_url == "https://api.openai.com/v1/responses"
    assert result["summary"] == "Summary"


def test_summary_context_is_bounded_and_reports_omissions() -> None:
    impact = {
        "symbol": {"file": "a.py", "line": 1, "qualname": "check"},
        "caller_paths": [],
        "affected_routes": [],
        "related_tests": [],
    }
    evidence = {"impacts": [impact] * 100, "source_hashes": {"a.py": "private-metadata"}}
    response = io.BytesIO(b'{"response":"Partial report summary"}')
    with patch("change_impact.ai.urlopen", return_value=response) as request:
        result = summarize_impact(evidence, "ollama")
    payload = json.loads(request.call_args.args[0].data)
    assert len(payload["prompt"]) < 13000
    assert "private-metadata" not in payload["prompt"]
    assert result["summary_scope"]["total_impacts"] == 100
    assert result["summary_scope"]["truncated"]
    assert result["evidence"] is evidence


def test_http_error_does_not_expose_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    failure = HTTPError("https://api.openai.com/v1/responses", 401, "test-only-key", {}, None)
    with patch("change_impact.ai.urlopen", side_effect=failure):
        with pytest.raises(RuntimeError, match="HTTP 401") as result:
            summarize_impact({}, "openai")
    assert "test-only-key" not in str(result.value)


def test_invalid_online_structure_is_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    with patch("change_impact.ai.urlopen", return_value=io.BytesIO(b'{"output":null}')):
        with pytest.raises(RuntimeError, match="invalid output structure"):
            summarize_impact({}, "openai")
