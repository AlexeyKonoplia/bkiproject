from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.clients.app_api import UpstreamApiError, UpstreamApiTimeout, post_json
from app.security.jwt import user_required

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(user_required)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=3)
    history: list[ChatMessage] = Field(default_factory=list)
    source_document_id: Optional[UUID] = None
    top_k: int = Field(5, ge=1, le=25)
    doc_year_from: Optional[int] = None
    doc_year_to: Optional[int] = None
    doc_category: Optional[str] = None
    answer_mode: Literal["brief", "detailed", "extract"] = "detailed"


class ChatResponse(BaseModel):
    answer_text: str
    sources: list[dict]
    ask_event_id: str
    request_id: str
    retrieved_chunks: int


def _build_chat_prompt(message: str, history: list[ChatMessage]) -> str:
    recent_history = history[-6:]
    if not recent_history:
        return message

    transcript = []
    for item in recent_history:
        speaker = "Пользователь" if item.role == "user" else "Ассистент"
        transcript.append(f"{speaker}: {item.content.strip()}")

    transcript.append(f"Пользователь: {message.strip()}")
    transcript.append("Ответь на последнее сообщение пользователя, учитывая предыдущий диалог.")
    return "\n".join(transcript)


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
) -> ChatResponse:
    authorization = request.headers.get("authorization")
    payload = {
        "question": req.message,
        "question_for_prompt": _build_chat_prompt(req.message, req.history),
        "top_k": req.top_k,
        "source_document_id": str(req.source_document_id) if req.source_document_id else None,
        "doc_year_from": req.doc_year_from,
        "doc_year_to": req.doc_year_to,
        "doc_category": req.doc_category,
        "answer_mode": req.answer_mode,
    }

    try:
        response_payload = await post_json("/ask", payload, authorization=authorization)
    except UpstreamApiTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except UpstreamApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload) from exc

    return ChatResponse(**response_payload)
