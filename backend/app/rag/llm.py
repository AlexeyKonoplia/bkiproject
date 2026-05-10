from __future__ import annotations

import json
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen

from app.config import settings


class OllamaModelNotAvailable(RuntimeError):
    pass


def _normalize_model_name(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def _ollama_tags_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/tags"


@lru_cache(maxsize=32)
def list_local_ollama_models(base_url: str) -> tuple[str, ...]:
    try:
        with urlopen(_ollama_tags_url(base_url), timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise OllamaModelNotAvailable(
            f"Ollama is unavailable at {base_url}. Check that the ollama service is running."
        ) from exc

    models = payload.get("models", [])
    return tuple(str(model.get("name", "")).strip() for model in models if model.get("name"))


def ensure_ollama_model_available(*, model: str, base_url: str) -> None:
    local_models = set(list_local_ollama_models(base_url))
    normalized_model = _normalize_model_name(model)
    if model in local_models or normalized_model in local_models:
        return

    installed = ", ".join(sorted(local_models)) or "none"
    raise OllamaModelNotAvailable(
        f"Ollama model '{model}' is not installed. "
        f"Run: docker compose exec ollama ollama pull {model}. "
        f"Installed models: {installed}."
    )


def build_chat_llm(*, model: str | None = None) -> ChatOllama:
    from langchain_ollama import ChatOllama

    selected_model = model or settings.LLM_MODEL
    ensure_ollama_model_available(
        model=selected_model,
        base_url=settings.OLLAMA_BASE_URL,
    )
    return ChatOllama(
        model=selected_model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
        num_ctx=settings.LLM_NUM_CTX,
        num_predict=settings.LLM_NUM_PREDICT,
        keep_alive=settings.LLM_KEEP_ALIVE,
    )
