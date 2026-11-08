import pytest


@pytest.fixture(autouse=True)
def isolated_model_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANGE_IMPACT_CONFIG_DIR", str(tmp_path / "model-settings"))
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "CHANGE_IMPACT_CUSTOM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
