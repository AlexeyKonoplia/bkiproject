from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List
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
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


async def _get_user_roles(session: AsyncSession, *, user_id: UUID) -> List[str]:
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    res = await session.execute(stmt)
    return [r[0] for r in res.all()]


async def get_current_actor(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> Actor:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = UUID(payload["sub"])
        roles = payload.get("roles", []) or []
    except (JWTError, KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e

    user_stmt = select(User).where(User.id == user_id)
    user_res = await session.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not roles:
        roles = await _get_user_roles(session, user_id=user_id)

    return Actor(user_id=user_id, username=user.username, roles=roles)
