from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from app.security.jwt import Actor, get_current_actor


def require_roles(*allowed_roles: str) -> Callable[..., Actor]:
    """
    Dependency factory: требует, чтобы у actor были хотя бы одна из ролей.
    """

    async def _checker(actor: Actor = Depends(get_current_actor)) -> Actor:
        if not any(r in actor.roles for r in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return actor

    return _checker


admin_required = require_roles("admin")
user_required = require_roles("user", "admin")


