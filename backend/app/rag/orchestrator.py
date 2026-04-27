from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingest.embedder import embed_texts
from app.rag.prompts import build_user_prompt, system_prompt_russian
from app.rag.retrieval import RetrievedChunk, keyword_search, literal_search, similarity_search

INSUFFICIENT_INFO_ANSWER = "Insufficient information to answer."


def build_sources_payload(chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "source_document_id": chunk.source_document_id,
            "file_name": chunk.file_name,
            "page_number": chunk.page_number,
            "chunk_text": chunk.chunk_text,
        }
        for chunk in chunks
    ]


def merge_retrieved_chunks(
    *,
    literal_chunks: List[RetrievedChunk],
    semantic_chunks: List[RetrievedChunk],
    keyword_chunks: List[RetrievedChunk],
    top_k: int,
) -> List[RetrievedChunk]:
    merged_chunks: List[RetrievedChunk] = []
    seen_chunk_ids: set[str] = set()

    # Prefer exact keyword hits first, but still keep semantic recall in the mix.
    max_len = max(len(literal_chunks), len(keyword_chunks), len(semantic_chunks))
    for idx in range(max_len):
        for chunk_list in (literal_chunks, keyword_chunks, semantic_chunks):
            if idx >= len(chunk_list):
                continue
            chunk = chunk_list[idx]
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            merged_chunks.append(chunk)
            if len(merged_chunks) >= top_k:
                return merged_chunks

    return merged_chunks


async def retrieve_relevant_chunks(
    session: AsyncSession,
    *,
    question: str,
    top_k: int,
    source_document_id: Optional[UUID] = None,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    literal_chunks: List[RetrievedChunk] = await literal_search(
        session,
        query_text=question,
        top_k=top_k,
        source_document_id=source_document_id,
        doc_year_from=doc_year_from,
        doc_year_to=doc_year_to,
        doc_category=doc_category,
    )

    keyword_chunks: List[RetrievedChunk] = await keyword_search(
        session,
        query_text=question,
        top_k=top_k,
        source_document_id=source_document_id,
        doc_year_from=doc_year_from,
        doc_year_to=doc_year_to,
        doc_category=doc_category,
    )

    exact_first_chunks = merge_retrieved_chunks(
        literal_chunks=literal_chunks,
        semantic_chunks=[],
        keyword_chunks=keyword_chunks,
        top_k=top_k,
    )
    if len(exact_first_chunks) >= top_k:
        return exact_first_chunks

    semantic_chunks: List[RetrievedChunk] = []
    query_embeddings = embed_texts(
        [question],
        embedding_model=settings.EMBEDDING_MODEL,
        ollama_base_url=settings.OLLAMA_BASE_URL,
    )
    query_vector = query_embeddings[0] if query_embeddings else []
    if query_vector:
        semantic_chunks = await similarity_search(
            session,
            query_vector=query_vector,
            top_k=top_k,
            source_document_id=source_document_id,
            doc_year_from=doc_year_from,
            doc_year_to=doc_year_to,
            doc_category=doc_category,
        )

    return merge_retrieved_chunks(
        literal_chunks=literal_chunks,
        semantic_chunks=semantic_chunks,
        keyword_chunks=keyword_chunks,
        top_k=top_k,
    )


async def answer_question(
    session: AsyncSession,
    *,
    question: str,
    question_for_prompt: Optional[str] = None,
    top_k: int,
    source_document_id: Optional[UUID] = None,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> Dict[str, Any]:
    chunks = await retrieve_relevant_chunks(
        session,
        question=question,
        top_k=top_k,
        source_document_id=source_document_id,
        doc_year_from=doc_year_from,
        doc_year_to=doc_year_to,
        doc_category=doc_category,
    )

    if not chunks:
        return {
            "answer_text": INSUFFICIENT_INFO_ANSWER,
            "sources": [],
            "retrieved_chunks": 0,
        }

    context_with_sources: List[tuple[str, str]] = []
    sources = build_sources_payload(chunks)
    for index, chunk in enumerate(chunks, start=1):
        source_label = f"[source{index}] file={chunk.file_name}, page={chunk.page_number}"
        context_with_sources.append((source_label, chunk.chunk_text))

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

    if settings.ENABLE_SELF_CORRECTION:
        verification_sys = (
            "You are a RAG verifier. Determine whether the answer is fully supported "
            "by the provided context. If the answer contains claims not present in the "
            "context, or the context is insufficient, return verdict=\"not_supported\". "
            "Return strict JSON only: "
            "{\"verdict\":\"supported|not_supported\",\"missing\":[\"...\"],\"notes\":\"...\"}."
        )
        context_for_verification = "\n\n".join(
            [f"{label}\n{chunk_text}" for label, chunk_text in context_with_sources]
        )
        verification_user = (
            f"Question:\n{prompt_question}\n\n"
            f"Model answer:\n{answer_text}\n\n"
            f"Context:\n{context_for_verification}\n\n"
            "Check whether the answer is supported by the context."
        )
        verification_messages = [SystemMessage(verification_sys), HumanMessage(verification_user)]
        verification_llm_response = llm.invoke(verification_messages)
        verification_raw = getattr(verification_llm_response, "content", str(verification_llm_response))

        verdict = "supported"
        try:
            start = verification_raw.find("{")
            end = verification_raw.rfind("}")
            payload = verification_raw[start : end + 1] if start != -1 and end != -1 else verification_raw
            parsed = json.loads(payload)
            verdict = parsed.get("verdict", verdict)
        except Exception:
            verdict = "supported"

        if verdict != "supported":
            answer_text = INSUFFICIENT_INFO_ANSWER

    return {
        "answer_text": answer_text,
        "sources": sources,
        "retrieved_chunks": len(chunks),
    }
