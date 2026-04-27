from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Role, User, UserRole
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    username: str
    roles: List[str]


def _normalize_roles(raw_roles: Any) -> list[str]:
    if isinstance(raw_roles, str):
        candidates: Iterable[str] = (part.strip() for part in raw_roles.split(","))
    elif isinstance(raw_roles, list):
        candidates = (str(part).strip() for part in raw_roles)
    else:
        return []
    return sorted({role for role in candidates if role})


def _decode_local_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def _decode_portal_token(token: str) -> dict[str, Any]:
    decode_kwargs: dict[str, Any] = {}
    if settings.PORTAL_JWT_AUDIENCE:
        decode_kwargs["audience"] = settings.PORTAL_JWT_AUDIENCE
    if settings.PORTAL_JWT_ISSUER:
        decode_kwargs["issuer"] = settings.PORTAL_JWT_ISSUER
    return jwt.decode(
        token,
        settings.PORTAL_JWT_SECRET,
        algorithms=[settings.PORTAL_JWT_ALGORITHM],
        **decode_kwargs,
    )


async def _get_user_roles(session: AsyncSession, *, user_id: UUID) -> List[str]:
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    res = await session.execute(stmt)
    return [row[0] for row in res.all()]


async def _ensure_role(session: AsyncSession, role_name: str) -> Role:
    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        role = Role(name=role_name)
        session.add(role)
        await session.flush()
    return role


async def _sync_user_roles(session: AsyncSession, *, user: User, role_names: list[str]) -> list[str]:
    normalized = _normalize_roles(role_names) or ["user"]
    existing_roles = {
        role.name: role
        for role in (
            await session.execute(select(Role).where(Role.name.in_(normalized)))
        ).scalars()
    }
    for role_name in normalized:
        if role_name not in existing_roles:
            existing_roles[role_name] = await _ensure_role(session, role_name)

    existing_links = (
        await session.execute(select(UserRole).where(UserRole.user_id == user.id))
    ).scalars().all()
    linked_role_ids = {link.role_id for link in existing_links}
    desired_role_ids = {existing_roles[role_name].id for role_name in normalized}

    for role_name in normalized:
        role = existing_roles[role_name]
        if role.id not in linked_role_ids:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    for link in existing_links:
        if link.role_id not in desired_role_ids:
            await session.delete(link)

    await session.flush()
    return normalized


async def _get_or_create_portal_actor(session: AsyncSession, payload: dict[str, Any]) -> Actor:
    username = str(
        payload.get(settings.PORTAL_USERNAME_CLAIM)
        or payload.get(settings.PORTAL_SUB_CLAIM)
        or ""
    ).strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal token missing username")

    if not settings.PORTAL_AUTO_PROVISION_USERS:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal user not provisioned")
        roles = await _get_user_roles(session, user_id=user.id)
        return Actor(user_id=user.id, username=user.username, roles=roles)

    role_names = _normalize_roles(payload.get(settings.PORTAL_ROLES_CLAIM)) or ["user"]

    async with session.begin():
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None:
            user = User(username=username, password_hash="!")
            session.add(user)
            await session.flush()
        roles = await _sync_user_roles(session, user=user, role_names=role_names)

    return Actor(user_id=user.id, username=user.username, roles=roles)


async def get_current_actor(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> Actor:
    local_error: Exception | None = None

    if settings.AUTH_MODE in {"local", "hybrid"}:
        try:
            payload = _decode_local_token(token)
            user_id = UUID(str(payload["sub"]))
            roles = _normalize_roles(payload.get("roles"))
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not roles:
                roles = await _get_user_roles(session, user_id=user_id)
            return Actor(user_id=user_id, username=user.username, roles=roles)
        except (JWTError, KeyError, ValueError, HTTPException) as exc:
            local_error = exc

    if settings.AUTH_MODE in {"portal", "hybrid"}:
        try:
            payload = _decode_portal_token(token)
            return await _get_or_create_portal_actor(session, payload)
        except (JWTError, KeyError, ValueError, HTTPException) as exc:
            if settings.AUTH_MODE == "portal":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token") from exc

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from local_error


async def user_required(actor: Actor = Depends(get_current_actor)) -> Actor:
    if not any(role in actor.roles for role in ("user", "admin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return actor


async def admin_required(actor: Actor = Depends(get_current_actor)) -> Actor:
    if "admin" not in actor.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return actor
