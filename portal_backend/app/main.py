from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.config import settings
from app.db.session import SessionLocal


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PORTAL_TITLE, version="0.1.0")
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(chat_router)

    @app.on_event("startup")
    async def _ensure_document_metadata_columns() -> None:
        async with SessionLocal() as session:
            await session.execute(
                text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS description TEXT")
            )
            await session.execute(
                text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS uploaded_by UUID")
            )
            await session.commit()

    return app


app = create_app()
