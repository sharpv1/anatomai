from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.identity.policy import authorize
from app.identity.security import cookie_token, require_origin
from app.identity.service import Identity, authenticate, require_csrf


def current_identity(request: Request) -> Identity:
    identity: Identity = request.state.identity
    return identity


def current_db(request: Request) -> AsyncSession:
    db: AsyncSession = request.state.identity_db
    return db


@asynccontextmanager
async def identity_transaction(request: Request) -> AsyncIterator[AsyncSession]:
    try:
        async with request.app.state.database.sessions.begin() as db:
            yield db
    except SQLAlchemyError:
        raise ApplicationError("SERVICE_NOT_READY", "Сервис временно недоступен.", 503) from None


async def enforce_access(request: Request) -> AsyncIterator[None]:
    policy = getattr(request.scope.get("endpoint"), "medexa_permission", None)
    if policy == "public.health":
        yield
        return
    settings: Settings = request.app.state.settings
    if policy in ("public.telegram_exchange", "public.logout"):
        require_origin(request.headers, settings, mutation=True)
        yield
        return
    if not isinstance(policy, str):
        raise ApplicationError(
            "ACCESS_DENIED", "Для этого маршрута не задана политика доступа.", 403
        )
    require_origin(
        request.headers, settings, mutation=request.method not in ("GET", "HEAD", "OPTIONS")
    )
    try:
        async with request.app.state.database.sessions.begin() as db:
            identity = await authenticate(db, cookie_token(request), settings)
            authorize(identity.roles, policy)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                require_csrf(identity, request.headers.get("x-csrf-token"))
            request.state.identity = identity
            request.state.identity_db = db
            yield
    except SQLAlchemyError:
        raise ApplicationError("SERVICE_NOT_READY", "Сервис временно недоступен.", 503) from None
