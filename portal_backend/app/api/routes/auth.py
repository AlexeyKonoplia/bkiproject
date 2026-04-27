from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.clients.app_api import UpstreamApiError, post_json
from app.security.jwt import Actor, user_required

router = APIRouter(prefix="/api/auth", tags=["portal-auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=3)


@router.post("/login")
async def login(req: LoginRequest) -> dict:
    try:
        payload = await post_json("/auth/login", req.model_dump())
    except UpstreamApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload) from exc
    return payload


@router.get("/me")
async def me(actor: Actor = Depends(user_required)) -> dict:
    return {
        "user_id": str(actor.user_id),
        "username": actor.username,
        "roles": actor.roles,
    }

