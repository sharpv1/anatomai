from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api.health import router
from app.core.config import Settings
from app.core.errors import ErrorEnvelope, register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.database import Database
from app.identity.api import router as identity_router
from app.identity.dependencies import enforce_access
from app.identity.security import IdentityRequestMiddleware


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
    return app
