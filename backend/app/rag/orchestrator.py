from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingest.embedder import embed_texts
from app.rag.prompts import build_user_prompt, system_prompt_russian
from app.rag.retrieval import RetrievedChunk, similarity_search


async def answer_question(
    session: AsyncSession,
    *,
    question: str,
    question_for_prompt: Optional[str] = None,
    top_k: int,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Вопрос -> (embedding) -> Retrieval (pgvector) -> Prompt -> LLM -> answer + sources.
    """
    # Embedding запроса (локальный Ollama)
    q_vec = embed_texts(
        [question],
        embedding_model=settings.EMBEDDING_MODEL,
        ollama_base_url=settings.OLLAMA_BASE_URL,
    )
    query_vector = q_vec[0] if q_vec else []

    chunks: List[RetrievedChunk] = await similarity_search(
        session,
        query_vector=query_vector,
        top_k=top_k,
        doc_year_from=doc_year_from,
        doc_year_to=doc_year_to,
        doc_category=doc_category,
    )

    # Подготовка контекста с источниками для цитирования
    context_with_sources: List[tuple[str, str]] = []
    sources: List[Dict[str, Any]] = []
    for i, c in enumerate(chunks, start=1):
        source_label = f"[source{i}] file={c.file_name}, page={c.page_number}"
        context_with_sources.append((source_label, c.chunk_text))
        sources.append(
            {
                "chunk_id": c.chunk_id,
                "file_name": c.file_name,
                "page_number": c.page_number,
            }
        )

    prompt_question = question_for_prompt or question
    user_prompt = build_user_prompt(prompt_question, context_with_sources)
    sys_prompt = system_prompt_russian()

    llm = ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
    )

    messages = [SystemMessage(sys_prompt), HumanMessage(user_prompt)]
    llm_response = llm.invoke(messages)

    answer_text = getattr(llm_response, "content", str(llm_response))

    # Self-correction: проверка, что ответ опирается на предоставленный контекст.
    if settings.ENABLE_SELF_CORRECTION:
        verification_sys = (
            "Ты — проверяющий RAG. Твоя задача: определить, поддерживается ли ответ контекстом. "
            "Если в ответе есть утверждения, которых нет в контексте, или контекст не содержит нужных данных — verdict должен быть not_supported. "
            "Верни строго JSON в формате: "
            "{\"verdict\":\"supported|not_supported\",\"missing\":[\"...\"],\"notes\":\"...\"}."
        )
        context_for_verification = "\n\n".join(
            [f"{label}\n{chunk_text}" for label, chunk_text in context_with_sources]
        )
        verification_user = (
            f"Вопрос:\n{prompt_question}\n\n"
            f"Ответ модели:\n{answer_text}\n\n"
            f"Контекст:\n{context_for_verification}\n\n"
            "Проверь поддерживаемость ответа контекстом."
        )
        verification_messages = [SystemMessage(verification_sys), HumanMessage(verification_user)]
        verification_llm_response = llm.invoke(verification_messages)
        verification_raw = getattr(verification_llm_response, "content", str(verification_llm_response))

        verdict = "not_supported"
        try:
            start = verification_raw.find("{")
            end = verification_raw.rfind("}")
            payload = verification_raw[start : end + 1] if start != -1 and end != -1 else verification_raw
            parsed = json.loads(payload)
            verdict = parsed.get("verdict", verdict)
        except Exception:
            verdict = "not_supported"

        if verdict != "supported":
            answer_text = "Информация недостаточна для ответа"

    return {
        "answer_text": answer_text,
        "sources": sources,
        "retrieved_chunks": len(chunks),
    }


