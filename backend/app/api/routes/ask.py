from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AuditLog, AskEvent, SourceDocument, TextChunk
from app.db.session import get_db
from app.rag.orchestrator import answer_question, retrieve_relevant_chunks
from app.rag.retrieval import RetrievedChunk
from app.security.jwt import Actor
from app.security.redaction import redact_text
from app.security.rbac import user_required

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    question_for_prompt: Optional[str] = None
    top_k: int = Field(5, ge=1, le=25)
    source_document_id: Optional[UUID] = None

    # Filtering by document metadata.
    doc_year_from: Optional[int] = None
    doc_year_to: Optional[int] = None
    doc_category: Optional[str] = None
    answer_mode: Literal["brief", "detailed", "extract"] = "detailed"

    # Optional request id for traceability.
    request_id: Optional[str] = None


class AskResponse(BaseModel):
    ask_event_id: str
    request_id: str
    answer_text: str
    sources: list[Dict[str, Any]]
    retrieved_chunks: int


class RetrievedChunkResponse(BaseModel):
    chunk_id: str
    source_document_id: str
    file_name: str
    page_number: int
    chunk_text: str


class LastAskChunksResponse(BaseModel):
    ask_event_id: str
    request_id: str
    question_text: str
    chunks: list[RetrievedChunkResponse]
    retrieved_chunks: int


def _safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_uuid(value: Any) -> Optional[UUID]:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _normalize_top_k(value: Any) -> int:
    top_k = _safe_int(value) or 5
    return max(1, min(25, top_k))


def _normalize_retrieved_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sources = payload.get("retrieved_sources")
    if not isinstance(raw_sources, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue

        chunk_id = str(item.get("chunk_id") or "").strip()
        source_document_id = str(item.get("source_document_id") or "").strip()
        file_name = str(item.get("file_name") or "").strip()
        page_number = _safe_int(item.get("page_number"))
        if not chunk_id or not source_document_id or page_number is None:
            continue

        normalized.append(
            {
                "chunk_id": chunk_id,
                "source_document_id": source_document_id,
                "file_name": file_name,
                "page_number": page_number,
                "chunk_text": str(item.get("chunk_text") or "").strip(),
            }
        )

    return normalized


def _serialize_chunks(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
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


async def _get_latest_ask_event(session: AsyncSession, *, actor_user_id: UUID) -> AskEvent | None:
    stmt = (
        select(AskEvent)
        .where(AskEvent.actor_user_id == actor_user_id)
        .order_by(AskEvent.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _get_ask_audit_log(session: AsyncSession, *, request_id: str) -> AuditLog | None:
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.request_id == request_id,
            AuditLog.action == "ask",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_chunks_from_sources(
    session: AsyncSession,
    *,
    retrieved_sources: list[dict[str, Any]],
) -> list[RetrievedChunk]:
    chunk_ids: list[UUID] = []
    ordered_chunk_ids: list[str] = []
    for source in retrieved_sources:
        chunk_id = source["chunk_id"]
        try:
            chunk_uuid = UUID(chunk_id)
        except ValueError:
            continue
        chunk_ids.append(chunk_uuid)
        ordered_chunk_ids.append(chunk_id)

    if not chunk_ids:
        return []

    stmt = (
        select(TextChunk, SourceDocument.file_name)
        .join(SourceDocument, TextChunk.source_document_id == SourceDocument.id)
        .where(TextChunk.id.in_(chunk_ids))
    )
    rows = (await session.execute(stmt)).all()

    chunks_by_id = {
        str(chunk.id): RetrievedChunk(
            chunk_id=str(chunk.id),
            source_document_id=str(chunk.source_document_id),
            file_name=file_name,
            page_number=chunk.page_number,
            chunk_text=chunk.chunk_text,
        )
        for chunk, file_name in rows
    }

    ordered_chunks: list[RetrievedChunk] = []
    for chunk_id in ordered_chunk_ids:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is not None:
            ordered_chunks.append(chunk)
    return ordered_chunks


async def _fallback_retrieve_last_chunks(
    session: AsyncSession,
    *,
    ask_event: AskEvent,
    audit_payload: dict[str, Any],
) -> list[RetrievedChunk]:
    question_text = str(audit_payload.get("query") or ask_event.query_text_redacted).strip()
    if not question_text:
        return []

    return await retrieve_relevant_chunks(
        session,
        question=question_text,
        top_k=_normalize_top_k(audit_payload.get("top_k")),
        source_document_id=_safe_uuid(audit_payload.get("source_document_id")),
        doc_year_from=_safe_int(audit_payload.get("doc_year_from")),
        doc_year_to=_safe_int(audit_payload.get("doc_year_to")),
        doc_category=str(audit_payload.get("doc_category") or "").strip() or None,
    )


async def resolve_last_ask_chunks(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
) -> dict[str, Any]:
    ask_event = await _get_latest_ask_event(session, actor_user_id=actor_user_id)
    if ask_event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ask requests found for the current user",
        )

    audit_log = await _get_ask_audit_log(session, request_id=ask_event.request_id)
    audit_payload = audit_log.redacted_payload if audit_log and isinstance(audit_log.redacted_payload, dict) else {}

    chunks = await _load_chunks_from_sources(
        session,
        retrieved_sources=_normalize_retrieved_sources(audit_payload),
    )
    if not chunks:
        chunks = await _fallback_retrieve_last_chunks(
            session,
            ask_event=ask_event,
            audit_payload=audit_payload,
        )

    question_text = str(audit_payload.get("query") or ask_event.query_text_redacted).strip()
    return {
        "ask_event_id": str(ask_event.id),
        "request_id": ask_event.request_id,
        "question_text": question_text,
        "chunks": _serialize_chunks(chunks),
        "retrieved_chunks": len(chunks),
    }


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    session: AsyncSession = Depends(get_db),
    actor: Actor = Depends(user_required),
) -> AskResponse:
    request_id = req.request_id or str(uuid4())

    redacted_question = redact_text(req.question)
    redacted_question_for_prompt = (
        redact_text(req.question_for_prompt)
        if req.question_for_prompt
        else redacted_question
    )

    rag_result = await answer_question(
        session,
        question=req.question,
        question_for_prompt=redacted_question_for_prompt,
        top_k=req.top_k,
        source_document_id=req.source_document_id,
        doc_year_from=req.doc_year_from,
        doc_year_to=req.doc_year_to,
        doc_category=req.doc_category,
        answer_mode=req.answer_mode,
    )

    ask_event = AskEvent(
        actor_user_id=actor.user_id,
        created_at=datetime.now(timezone.utc),
        request_id=request_id,
        query_text_redacted=redacted_question,
        model=settings.LLM_MODEL,
        status="ok",
    )
    session.add(ask_event)
    await session.flush()

    session.add(
        AuditLog(
            actor_user_id=actor.user_id,
            created_at=datetime.now(timezone.utc),
            action="ask",
            request_id=request_id,
            redacted_payload={
                "query": redacted_question,
                "query_for_prompt": redacted_question_for_prompt,
                "top_k": req.top_k,
                "source_document_id": str(req.source_document_id) if req.source_document_id else None,
                "doc_year_from": req.doc_year_from,
                "doc_year_to": req.doc_year_to,
                "doc_category": req.doc_category,
                "answer_mode": req.answer_mode,
                "retrieved_chunks": rag_result["retrieved_chunks"],
                "retrieved_sources": rag_result["sources"],
            },
            status="ok",
        )
    )
    await session.commit()

    return AskResponse(
        ask_event_id=str(ask_event.id),
        request_id=request_id,
        answer_text=rag_result["answer_text"],
        sources=rag_result["sources"],
        retrieved_chunks=rag_result["retrieved_chunks"],
    )


@router.get("/ask/last-chunks", response_model=LastAskChunksResponse)
async def get_last_ask_chunks(
    session: AsyncSession = Depends(get_db),
    actor: Actor = Depends(user_required),
) -> LastAskChunksResponse:
    return LastAskChunksResponse(
        **(await resolve_last_ask_chunks(session, actor_user_id=actor.user_id))
    )
