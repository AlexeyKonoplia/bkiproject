import asyncio
import logging

from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from app.api.routes.ask import router as ask_router
from app.api.routes.auth import router as auth_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.health import router as health_router
from app.api.routes.tester_ui import router as tester_ui_router
from app.api.routes.upload import router as upload_router
from app.config import settings
from app.db.models import Role, User, UserRole
from app.db.session import SessionLocal
from app.security.jwt import hash_password

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="bki-support-rag", version="0.1.0")
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(tester_ui_router)
    app.include_router(ask_router)
    app.include_router(upload_router)
    app.include_router(feedback_router)

    @app.on_event("startup")
    async def _seed_admin() -> None:
        if not settings.ENABLE_BOOTSTRAP_ADMIN:
            return

        last_err: Exception | None = None
        for attempt in range(1, 31):
            try:
                async with SessionLocal() as session:
                    await session.execute(text("SELECT 1"))

                    for role_name in ("user", "admin"):
                        role = (
                            await session.execute(select(Role).where(Role.name == role_name))
                        ).scalar_one_or_none()
                        if role is None:
                            session.add(Role(name=role_name))
                            await session.flush()

                    admin_user = (
                        await session.execute(
                            select(User).where(User.username == settings.ADMIN_USERNAME)
                        )
                    ).scalar_one_or_none()
                    admin_role_id = (
                        await session.execute(select(Role.id).where(Role.name == "admin"))
                    ).scalar_one()

                    if admin_user is None:
                        admin_user = User(
                            username=settings.ADMIN_USERNAME,
                            password_hash=hash_password(settings.ADMIN_PASSWORD),
                        )
                        session.add(admin_user)
                        await session.flush()

                    existing = (
                        await session.execute(
                            select(UserRole).where(
                                UserRole.user_id == admin_user.id,
                                UserRole.role_id == admin_role_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(UserRole(user_id=admin_user.id, role_id=admin_role_id))

                    await session.commit()

                logger.info("Bootstrap admin seed completed on attempt %s", attempt)
                return
            except ProgrammingError as err:
                last_err = err
                logger.warning(
                    "Bootstrap admin is waiting for DB schema (attempt %s/30): %s",
                    attempt,
                    err,
                )
                await asyncio.sleep(2)
            except Exception as err:
                last_err = err
                logger.warning(
                    "Bootstrap admin retry after DB startup error (attempt %s/30): %s",
                    attempt,
                    err,
                )
                await asyncio.sleep(2)

        logger.exception("Bootstrap admin failed after all retries", exc_info=last_err)
        raise RuntimeError("DB seed admin failed after retries") from last_err

    return app


app = create_app()
