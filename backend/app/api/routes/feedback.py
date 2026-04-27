from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import AuditLog, Feedback, AskEvent
from app.db.session import get_db
from app.security.redaction import redact_text
from app.security.rbac import user_required

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    ask_event_id: UUID
    vote: int = Field(..., description="Use 1 for like, -1 for dislike")
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    ask_event_id: str


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    req: FeedbackRequest,
    session: AsyncSession = Depends(get_db),
    actor=Depends(user_required),
) -> FeedbackResponse:
    if req.vote not in (-1, 1):
        return FeedbackResponse(status="error", feedback_id="0", ask_event_id=str(req.ask_event_id))

    # Проверим, что ask_event существует (для корректности FK).
    ask_stmt = select(AskEvent).where(AskEvent.id == req.ask_event_id)
    ask_res = await session.execute(ask_stmt)
    ask_event = ask_res.scalar_one_or_none()
    if ask_event is None:
        return FeedbackResponse(status="error", feedback_id="0", ask_event_id=str(req.ask_event_id))

    comment_redacted = redact_text(req.comment) if req.comment else None

    fb = Feedback(
        ask_event_id=req.ask_event_id,
        created_at=datetime.now(timezone.utc),
        vote=req.vote,
        comment=comment_redacted,
    )
    session.add(fb)
    await session.flush()

    session.add(
        AuditLog(
            actor_user_id=actor.user_id,
            created_at=datetime.now(timezone.utc),
            action="feedback",
            request_id=str(ask_event.request_id),
            redacted_payload={
                "ask_event_id": str(req.ask_event_id),
                "vote": req.vote,
                "comment": comment_redacted,
            },
            status="ok",
        )
    )
    await session.commit()

    return FeedbackResponse(
        status="ok",
        feedback_id=str(fb.id),
        ask_event_id=str(req.ask_event_id),
    )

