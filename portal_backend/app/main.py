from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PORTAL_TITLE, version="0.1.0")
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(chat_router)
    return app


app = create_app()
