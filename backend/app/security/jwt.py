from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

PBKDF2_ITERATIONS = 600_000
PBKDF2_SCHEME = "pbkdf2_sha256"
LOCAL_TOKEN_KIND = "local"
PORTAL_TOKEN_KIND = "portal"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    username: str
    roles: List[str]


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(raw: str) -> bytes:
    return base64.b64decode(raw.encode("ascii"))


def _normalize_roles(raw_roles: Any) -> list[str]:
    if isinstance(raw_roles, str):
        candidates: Iterable[str] = (part.strip() for part in raw_roles.split(","))
    elif isinstance(raw_roles, list):
        candidates = (str(part).strip() for part in raw_roles)
    else:
        return []
    return sorted({role for role in candidates if role})


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if scheme != PBKDF2_SCHEME:
            return False
        iterations = int(iterations_raw)
        expected_digest = _b64decode(digest_raw)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode(salt_raw),
            iterations,
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(*, user_id: UUID, roles: List[str], expires_seconds: int = 3600) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=expires_seconds)
    payload = {
        "sub": str(user_id),
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "token_kind": LOCAL_TOKEN_KIND,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


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
    return [r[0] for r in res.all()]


async def _ensure_role(session: AsyncSession, role_name: str) -> Role:
    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        role = Role(name=role_name)
        session.add(role)
        await session.flush()
    return role


async def _sync_user_roles(session: AsyncSession, *, user: User, role_names: list[str]) -> list[str]:
    normalized = _normalize_roles(role_names)
    if not normalized:
        normalized = ["user"]

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

    role_names = _normalize_roles(payload.get(settings.PORTAL_ROLES_CLAIM))
    if not role_names:
        role_names = ["user"]

    async with session.begin():
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                password_hash="!",
            )
            session.add(user)
            await session.flush()

        roles = await _sync_user_roles(session, user=user, role_names=role_names)

    return Actor(user_id=user.id, username=user.username, roles=roles)


async def get_current_actor(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> Actor:
    if settings.AUTH_MODE not in {"local", "portal", "hybrid"}:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid AUTH_MODE")

    local_error: Exception | None = None
    if settings.AUTH_MODE in {"local", "hybrid"}:
        try:
            payload = _decode_local_token(token)
            user_id = UUID(payload["sub"])
            roles = _normalize_roles(payload.get("roles"))
            user_stmt = select(User).where(User.id == user_id)
            user_res = await session.execute(user_stmt)
            user = user_res.scalar_one_or_none()
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
            portal_error = exc
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from portal_error

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from local_error
