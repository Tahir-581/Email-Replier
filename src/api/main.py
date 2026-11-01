"""FastAPI application entrypoint for the dual dashboard API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import auth, campaigns, contacts, hr, settings, templates
from src.db.session import initialize_database, shutdown_database
from src.utils.config import settings as app_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    # Ensure admin user exists
    from src.api.deps import get_session as _  # noqa: F401
    from src.api.routers.auth import ensure_admin_user
    from src.db.session import get_session

    try:
        async with get_session() as db:
            await ensure_admin_user(db)
    except Exception:
        logger.warning("Could not seed admin user (tables may need migration)", exc_info=True)
    yield
    await shutdown_database()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Email Manager API",
        description="HR compliance replier + commercial email campaign manager",
        version="1.0.0",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in (app_settings.API_CORS_ORIGINS or "").split(",") if o.strip()]
    if not origins:
        origins = ["http://localhost:3000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api")
    app.include_router(hr.router, prefix="/api")
    app.include_router(contacts.router, prefix="/api")
    app.include_router(contacts.lists_router, prefix="/api")
    app.include_router(templates.router, prefix="/api")
    app.include_router(campaigns.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
