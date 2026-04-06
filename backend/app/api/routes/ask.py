from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AuditLog, AskEvent
from app.db.session import get_db
from app.rag.orchestrator import answer_question
from app.security.redaction import redact_text
from app.security.rbac import user_required

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = Field(5, ge=1, le=25)

    # Фильтрация по метаданным (2024-2025 и т.п.)
    doc_year_from: Optional[int] = None
    doc_year_to: Optional[int] = None
    doc_category: Optional[str] = None

    # Для сквозной трассировки
    request_id: Optional[str] = None


class AskResponse(BaseModel):
    ask_event_id: str
    request_id: str
    answer_text: str
    sources: list[Dict[str, Any]]
    retrieved_chunks: int


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    session: AsyncSession = Depends(get_db),
    actor=Depends(user_required),
) -> AskResponse:
    request_id = req.request_id or str(uuid4())

    redacted_question = redact_text(req.question)

    # Получаем ответ до записи ask_event, чтобы логировать итоговый статус.
    rag_result = await answer_question(
        session,
        question=req.question,
        question_for_prompt=redacted_question,
        top_k=req.top_k,
        doc_year_from=req.doc_year_from,
        doc_year_to=req.doc_year_to,
        doc_category=req.doc_category,
    )

    async with session.begin():
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
                    "top_k": req.top_k,
                    "doc_year_from": req.doc_year_from,
                    "doc_year_to": req.doc_year_to,
                    "doc_category": req.doc_category,
                    "retrieved_chunks": rag_result["retrieved_chunks"],
                },
                status="ok",
            )
        )

    return AskResponse(
        ask_event_id=str(ask_event.id),
        request_id=request_id,
        answer_text=rag_result["answer_text"],
        sources=rag_result["sources"],
        retrieved_chunks=rag_result["retrieved_chunks"],
    )

