import io
import json
from unittest.mock import patch

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
    response = io.BytesIO(json.dumps({"output": [{"content": [{"type": "output_text", "text": "Summary"}]}]}).encode())
    with patch("change_impact.ai.urlopen", return_value=response) as request:
        result = summarize_impact({}, "openai", "test-model")
    assert request.call_args.args[0].full_url == "https://api.openai.com/v1/responses"
    assert result["summary"] == "Summary"
