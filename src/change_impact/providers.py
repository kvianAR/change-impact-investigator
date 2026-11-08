"""Provider model catalogs. Model IDs can also be entered without a catalog."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .http_client import open_request as urlopen


def model_catalog(connection) -> list[dict]:
    endpoint = connection.base_url + ("/api/tags" if connection.provider == "ollama" else "/models")
    headers = {"Accept": "application/json", "User-Agent": "ChangeImpactInvestigator"}
    if connection.api_key:
        headers["Authorization"] = f"Bearer {connection.api_key}"
    try:
        with urlopen(Request(endpoint, headers=headers), timeout=30) as response:
            data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise RuntimeError("The provider catalog exceeded the response limit")
        payload = json.loads(data)
        models = payload.get("models" if connection.provider == "ollama" else "data")
        if not isinstance(models, list):
            raise ValueError()
    except HTTPError as error:
        raise RuntimeError(f"Provider HTTP {error.code}. Check the endpoint and API key.") from None
    except (URLError, TimeoutError):
        raise RuntimeError(
            "Could not reach the provider. Check its endpoint and connection."
        ) from None
    except (ValueError, AttributeError, UnicodeError):
        raise RuntimeError("Provider returned an invalid model catalog") from None
    result = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("name") if connection.provider == "ollama" else model.get("id")
        if not isinstance(model_id, str) or not model_id or len(model_id) > 512:
            continue
        name = model.get("name") if connection.provider != "ollama" else model_id
        context = model.get("context_length")
        result[model_id] = {
            "id": model_id,
            "name": name if isinstance(name, str) else model_id,
            "context_length": context if isinstance(context, int) else None,
        }
        if len(result) >= 2000:
            break
    return sorted(result.values(), key=lambda item: item["id"].lower())
