from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.admin.api import router as admin_router
from app.admin.auth_api import router as mfa_router
from app.api.health import router
from app.attempts.api import router as attempts_router
from app.content.api import router as content_router
from app.core.config import Settings
from app.core.errors import ErrorEnvelope, register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.database import Database
from app.identity.api import router as identity_router
from app.identity.dependencies import enforce_access
from app.identity.security import IdentityRequestMiddleware
from app.imports.api import router as imports_router
from app.progress.api import router as progress_router
from app.publishing.api import router as publishing_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title="MEDEXA Backend",
        version="0.1.0",
        lifespan=lifespan,
        dependencies=[Depends(enforce_access, scope="function")],
        responses={
            status: {"model": ErrorEnvelope}
            for status in (400, 401, 403, 404, 405, 409, 412, 413, 422, 429, 500, 503)
        },
    )
    app.state.settings = settings
    app.add_middleware(IdentityRequestMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(router)
    app.include_router(identity_router)
    app.include_router(content_router)
    app.include_router(mfa_router)
    app.include_router(admin_router)
    app.include_router(imports_router)
    app.include_router(publishing_router)
    app.include_router(attempts_router)
    app.include_router(progress_router)
    return app
