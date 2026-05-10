import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag import llm


def test_model_check_accepts_explicit_installed_tag(monkeypatch):
    monkeypatch.setattr(llm, "list_local_ollama_models", lambda base_url: ("qwen2.5:7b",))

    llm.ensure_ollama_model_available(model="qwen2.5:7b", base_url="http://ollama:11434")


def test_model_check_accepts_latest_alias(monkeypatch):
    monkeypatch.setattr(llm, "list_local_ollama_models", lambda base_url: ("nomic-embed-text:latest",))

    llm.ensure_ollama_model_available(model="nomic-embed-text", base_url="http://ollama:11434")


def test_model_check_reports_pull_command(monkeypatch):
    monkeypatch.setattr(llm, "list_local_ollama_models", lambda base_url: ("gemma4:e4b",))

    with pytest.raises(llm.OllamaModelNotAvailable) as exc_info:
        llm.ensure_ollama_model_available(model="qwen2.5:7b", base_url="http://ollama:11434")

    assert "docker compose exec ollama ollama pull qwen2.5:7b" in str(exc_info.value)
