from __future__ import annotations

from typing import List

from langchain_ollama import OllamaEmbeddings


def embed_texts(
    texts: List[str],
    *,
    embedding_model: str,
    ollama_base_url: str,
) -> List[List[float]]:
    """
    Получает embeddings через локальный Ollama (контейнерный endpoint).
    """
    if not texts:
        return []

    embeddings = OllamaEmbeddings(model=embedding_model, base_url=ollama_base_url)
    return embeddings.embed_documents(texts)


