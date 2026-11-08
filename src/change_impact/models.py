"""Atomic model profiles, provider connections, and the active summary model."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .credentials import CredentialError, SystemCredentials

PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "requires_key": True,
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "requires_key": True,
    },
    "ollama": {
        "name": "Ollama",
        "base_url": "http://127.0.0.1:11434",
        "key_env": None,
        "requires_key": False,
    },
    "custom": {
        "name": "Custom API",
        "base_url": "",
        "key_env": "CHANGE_IMPACT_CUSTOM_API_KEY",
        "requires_key": False,
    },
}


class SettingsConflict(ValueError):
    pass


def settings_directory() -> Path:
    configured = os.environ.get("CHANGE_IMPACT_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ChangeImpactInvestigator"
    return (
        Path(
            os.environ.get("APPDATA")
            or os.environ.get("XDG_CONFIG_HOME")
            or Path.home() / ".config"
        )
        / "change-impact-investigator"
    )


def validate_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError("Enter a valid API key")
    value = value.strip()
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise ValueError("API keys must not contain whitespace or control characters")
    return value


def validate_endpoint(provider: str, value: str) -> str:
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    if provider in {"openai", "openrouter"}:
        if value and value.rstrip("/") != PROVIDERS[provider]["base_url"]:
            raise ValueError("Use Custom API for another endpoint")
        return PROVIDERS[provider]["base_url"]
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Enter an endpoint without credentials, query parameters, or fragments")
    try:
        local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        local = parsed.hostname == "localhost"
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Use HTTPS, or HTTP for a loopback endpoint")
    try:
        parsed.port
    except ValueError:
        raise ValueError("Invalid endpoint port") from None
    return value


@dataclass(frozen=True)
class ModelConnection:
    provider: str
    model: str
    base_url: str
    api_key: str | None = field(default=None, repr=False)
    max_output_tokens: int = 800
    profile_id: str | None = None


class ModelStore:
    def __init__(self, directory: Path | None = None, credentials=None):
        self.directory = directory or settings_directory()
        self.path = self.directory / "models.json"
        self.credentials = credentials if credentials is not None else SystemCredentials()
        self._mutex = threading.RLock()

    @staticmethod
    def _empty():
        return {"format": 1, "revision": 0, "providers": {}, "models": [], "active_model_id": None}

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.directory.is_symlink() or self.path.is_symlink():
            raise ValueError("Settings paths must not be symlinks")
        self.directory.chmod(0o700)
        with self._mutex, (self.directory / ".models.lock").open("a+b") as lock:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                if lock.read(1) == b"":
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists():
            return self._empty()
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                state.get("format") != 1
                or not isinstance(state.get("models"), list)
                or not isinstance(state.get("providers"), dict)
                or not isinstance(state.get("revision"), int)
            ):
                raise ValueError()
            if state["revision"] < 0 or "active_model_id" not in state:
                raise ValueError()
            for profile in state["models"]:
                if (
                    not isinstance(profile, dict)
                    or not all(
                        isinstance(profile.get(key), str)
                        for key in ("id", "provider", "model", "name")
                    )
                    or profile["provider"] not in PROVIDERS
                    or type(profile.get("max_output_tokens")) is not int
                ):
                    raise ValueError()
            if state["active_model_id"] is not None and not any(
                profile["id"] == state["active_model_id"] for profile in state["models"]
            ):
                raise ValueError()
            if any(
                provider not in PROVIDERS or not isinstance(entry, dict)
                for provider, entry in state["providers"].items()
            ):
                raise ValueError()
            return state
        except (ValueError, TypeError, AttributeError):
            raise ValueError(
                "Saved model settings are invalid. Restore the settings file before making changes."
            ) from None

    def _write(self, state):
        temporary = self.directory / f".models-{uuid.uuid4().hex}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(state, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def _key(self, state, provider):
        if state["providers"].get(provider, {}).get("saved_key"):
            try:
                value = self.credentials.get(provider)
                if value:
                    return value, "keychain"
            except CredentialError:
                environment = PROVIDERS[provider]["key_env"]
                if not environment or not os.environ.get(environment):
                    raise
        environment = PROVIDERS[provider]["key_env"]
        return (
            (os.environ.get(environment), "environment")
            if environment and os.environ.get(environment)
            else (None, "none")
        )

    def _public(self, state):
        providers = []
        for provider, default in PROVIDERS.items():
            entry = state["providers"].get(provider, {})
            try:
                key, source = self._key(state, provider)
                error = False
            except CredentialError:
                key, source, error = None, "unavailable", True
            providers.append(
                {
                    "id": provider,
                    "name": default["name"],
                    "base_url": entry.get("base_url", default["base_url"]),
                    "requires_key": default["requires_key"],
                    "key_available": bool(key),
                    "key_source": source,
                    "saved_key": bool(entry.get("saved_key")),
                    "key_error": error,
                }
            )
        return {
            "revision": state["revision"],
            "models": copy.deepcopy(state["models"]),
            "active_model_id": state["active_model_id"],
            "providers": providers,
            "secure_storage_available": self.credentials.available(),
        }

    def state(self):
        if not self.directory.exists():
            return self._public(self._empty())
        with self._locked():
            return self._public(self._read())

    def _provider_change(self, state, provider, data):
        if provider not in PROVIDERS:
            raise ValueError("Choose a supported provider")
        entry = state["providers"].setdefault(provider, {})
        if "base_url" in data:
            value = data["base_url"]
            if not isinstance(value, str):
                raise ValueError("Invalid endpoint")
            entry["base_url"] = validate_endpoint(provider, value)
        key = data.get("api_key")
        if key is not None and not isinstance(key, str):
            raise ValueError("API key must be text")
        remove = data.get("remove_key") is True
        if key and remove:
            raise ValueError("Choose either updating or removing the saved key")
        if not key and not remove:
            return None
        if provider == "ollama":
            raise ValueError("Ollama does not use an API key")
        validated = validate_key(key) if key else None
        old = self.credentials.get(provider)
        if remove:
            self.credentials.delete(provider)
            entry["saved_key"] = False
        else:
            self.credentials.set(provider, validated)
            entry["saved_key"] = True
        return provider, old

    def _mutate(self, operation, expected_revision):
        if expected_revision is not None and type(expected_revision) is not int:
            raise ValueError("Invalid settings revision")
        with self._locked():
            state = self._read()
            if expected_revision is not None and expected_revision != state["revision"]:
                raise SettingsConflict("Settings changed in another window. Review and save again.")
            undo = None
            try:
                undo = operation(state)
                state["revision"] += 1
                self._write(state)
            except Exception:
                if undo:
                    provider, previous = undo
                    try:
                        self.credentials.set(
                            provider, previous
                        ) if previous is not None else self.credentials.delete(provider)
                    except CredentialError:
                        raise CredentialError(
                            "Settings could not be saved. Recheck the provider key before retrying."
                        ) from None
                raise
            return self._public(state)

    def save_provider(self, provider, data, expected_revision=None):
        return self._mutate(
            lambda state: self._provider_change(state, provider, data), expected_revision
        )

    def save_model(self, data, expected_revision=None):
        provider, model = data.get("provider"), data.get("model")
        if (
            provider not in PROVIDERS
            or not isinstance(model, str)
            or not model.strip()
            or len(model) > 512
            or any(ord(character) < 32 for character in model)
        ):
            raise ValueError("Choose a provider and enter a model ID")
        name = data.get("name") or model.strip().rsplit("/", 1)[-1]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Model name must contain 1 to 100 characters")
        maximum = data.get("max_output_tokens", 800)
        if type(maximum) is not int or not 64 <= maximum <= 8192:
            raise ValueError("Output limit must be between 64 and 8192 tokens")

        def operation(state):
            profile_id = data.get("id")
            existing = next((item for item in state["models"] if item["id"] == profile_id), None)
            if profile_id and existing is None:
                raise ValueError("This saved model no longer exists")
            if len(state["models"]) >= 100 and existing is None:
                raise ValueError("A maximum of 100 models can be saved")
            # Validate activation before changing a credential so failures remain atomic.
            key, _ = self._key(state, provider)
            proposed_key = data.get("api_key") or (None if data.get("remove_key") else key)
            wants_active = data.get("activate") is True or (
                existing is not None
                and state["active_model_id"] == profile_id
                and data.get("activate") is not False
            )
            if wants_active and PROVIDERS[provider]["requires_key"] and not proposed_key:
                raise ValueError("Save the provider API key before activating this model")
            if provider == "custom" and not data.get(
                "base_url", state["providers"].get(provider, {}).get("base_url")
            ):
                raise ValueError("Enter the Custom API endpoint")
            undo = self._provider_change(state, provider, data)
            profile = {
                "id": profile_id or uuid.uuid4().hex,
                "provider": provider,
                "model": model.strip(),
                "name": name.strip(),
                "max_output_tokens": maximum,
            }
            if existing:
                existing.update(profile)
            else:
                state["models"].append(profile)
            if wants_active:
                state["active_model_id"] = profile["id"]
            elif state["active_model_id"] == profile["id"]:
                state["active_model_id"] = None
            return undo

        return self._mutate(operation, expected_revision)

    def activate(self, profile_id, expected_revision=None):
        def operation(state):
            profile = next((item for item in state["models"] if item["id"] == profile_id), None)
            if profile is None:
                raise ValueError("Saved model not found")
            key, _ = self._key(state, profile["provider"])
            if PROVIDERS[profile["provider"]]["requires_key"] and not key:
                raise ValueError("Save the provider API key before activating this model")
            state["active_model_id"] = profile_id

        return self._mutate(operation, expected_revision)

    def delete(self, profile_id, expected_revision=None):
        def operation(state):
            if not any(item["id"] == profile_id for item in state["models"]):
                raise ValueError("Saved model not found")
            state["models"] = [item for item in state["models"] if item["id"] != profile_id]
            if state["active_model_id"] == profile_id:
                state["active_model_id"] = None

        return self._mutate(operation, expected_revision)

    def connection(
        self, provider=None, model=None, key_override=None, base_url=None, require_key=True
    ):
        def resolve(state):
            profile = next(
                (item for item in state["models"] if item["id"] == state["active_model_id"]), None
            )
            selected = provider or (profile["provider"] if profile else None)
            if selected not in PROVIDERS:
                raise ValueError(
                    "No active model. Open the Models panel or select a provider explicitly."
                )
            use_profile = profile and profile["provider"] == selected and model is None
            selected_model = model or (
                profile["model"]
                if use_profile
                else {"openai": "gpt-4.1-mini", "ollama": "qwen3.5:2b-q4_K_M"}.get(selected)
            )
            if not selected_model:
                raise ValueError("Enter a model ID or activate a saved model")
            try:
                key = validate_key(key_override) if key_override else self._key(state, selected)[0]
            except CredentialError:
                if require_key:
                    raise
                key = None
            if require_key and PROVIDERS[selected]["requires_key"] and not key:
                raise ValueError(
                    f"Save a {PROVIDERS[selected]['name']} key in Models or set {PROVIDERS[selected]['key_env']}"
                )
            endpoint = (
                base_url
                if base_url is not None
                else state["providers"]
                .get(selected, {})
                .get("base_url", PROVIDERS[selected]["base_url"])
            )
            endpoint = validate_endpoint(selected, endpoint)
            return ModelConnection(
                selected,
                selected_model,
                endpoint,
                key,
                profile["max_output_tokens"] if use_profile else 800,
                profile["id"] if use_profile else None,
            )

        if not self.directory.exists():
            return resolve(self._empty())
        with self._locked():
            return resolve(self._read())
