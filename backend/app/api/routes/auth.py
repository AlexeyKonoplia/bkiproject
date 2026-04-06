from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role, User, UserRole
from app.db.session import get_db
from app.security.jwt import create_access_token, hash_password, verify_password
from app.security.rbac import admin_required

router = APIRouter(tags=["auth"])

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=3)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db)) -> LoginResponse:
    stmt = select(User).where(User.username == req.username)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    roles_stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    roles_res = await session.execute(roles_stmt)
    roles = [r[0] for r in roles_res.all()]

    token = create_access_token(user_id=user.id, roles=roles)
    return LoginResponse(access_token=token)


class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=3)
    roles: List[str] = Field(default_factory=lambda: ["user"])


@router.post("/admin/bootstrap")
async def admin_bootstrap(
    req: BootstrapRequest,
    session: AsyncSession = Depends(get_db),
    actor=Depends(admin_required),
):
    roles_allowed = {"user", "admin"}
    unknown = [r for r in req.roles if r not in roles_allowed]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown roles: {unknown}")

    async with session.begin():
        existing_user = (await session.execute(select(User).where(User.username == req.username))).scalar_one_or_none()
        if existing_user is not None:
            raise HTTPException(status_code=409, detail="User already exists")

        # Ensure roles exist
        role_ids: dict[str, UUID] = {}
        for role_name in req.roles:
            role_row = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
            if role_row is None:
                role_row = Role(name=role_name)
                session.add(role_row)
                await session.flush()
            role_ids[role_name] = role_row.id

        user = User(
            username=req.username,
            password_hash=hash_password(req.password),
        )
        session.add(user)
        await session.flush()

        for role_name in req.roles:
            session.add(UserRole(user_id=user.id, role_id=role_ids[role_name]))

    return {"status": "ok", "user_id": str(user.id), "roles": req.roles}

