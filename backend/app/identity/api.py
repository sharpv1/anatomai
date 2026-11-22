import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.health import Meta
from app.core.errors import ApplicationError
from app.identity.dependencies import current_db, current_identity, identity_transaction
from app.identity.models import UserSession
from app.identity.policy import access
from app.identity.schemas import (
    Envelope,
    LoginBody,
    Preferences,
    SessionSummary,
    SessionView,
    UserView,
)
from app.identity.security import COOKIE_NAME, cookie_token
from app.identity.service import (
    Identity,
    audit,
    auth_configuration,
    authenticate,
    login,
    require_csrf,
)
from app.identity.telegram import verify_init_data

router = APIRouter(prefix="/api/v1", tags=["identity"])


def user_view(identity: Identity) -> UserView:
    u = identity.user
    return UserView(
        id=u.id,
        telegram_user_id=str(u.telegram_user_id),
        first_name=u.first_name,
        last_name=u.last_name,
        username=u.username,
        photo_url=u.photo_url,
        language=u.language_code,
        timezone=u.timezone,
        version=u.version,
        roles=sorted(identity.roles),
    )


def session_view(identity: Identity) -> SessionView:
    return SessionView(
        id=identity.session.id,
        user=user_view(identity),
        expires_at=identity.session.expires_at,
        idle_expires_at=identity.session.idle_expires_at,
        csrf_token=identity.csrf.get_secret_value(),
    )


def meta(request: Request) -> Meta:
    return Meta(request_id=request.state.request_id, server_time=datetime.now(UTC))


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


@router.post("/auth/telegram", response_model=Envelope[SessionView])
@access("public.telegram_exchange")
async def telegram_login(
    body: LoginBody, request: Request, response: Response
) -> Envelope[SessionView]:
    settings = request.app.state.settings
    bot_token, _ = auth_configuration(settings)
    proof = verify_init_data(
        body.init_data.get_secret_value(), bot_token, max_age=settings.init_data_max_age_seconds
    )
    async with identity_transaction(request) as db:
        identity, created = await login(
            db,
            proof,
            cookie_token(request),
            settings,
            timezone=body.timezone,
            language=body.language,
            request_id=UUID(request.state.request_id),
        )
        result = session_view(identity)
    # Set-Cookie is constructed only after the transaction commits successfully.
    if created:
        response.set_cookie(
            COOKIE_NAME,
            identity.token.get_secret_value(),
            max_age=max(0, int((identity.session.expires_at - datetime.now(UTC)).total_seconds())),
            expires=identity.session.expires_at,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    return Envelope(data=result, meta=meta(request))


@router.get("/auth/session", response_model=Envelope[SessionView])
@access("identity.self.read")
async def restore_session(request: Request) -> Envelope[SessionView]:
    return Envelope(data=session_view(current_identity(request)), meta=meta(request))


@router.get("/users/me", response_model=Envelope[UserView])
@router.get("/me", response_model=Envelope[UserView])
@access("identity.self.read")
async def me(request: Request, response: Response) -> Envelope[UserView]:
    identity = current_identity(request)
    response.headers["ETag"] = f'"{identity.user.version}"'
    return Envelope(data=user_view(identity), meta=meta(request))


@router.patch("/me/preferences", response_model=Envelope[UserView])
@access("identity.preferences.write")
async def preferences(
    body: Preferences, request: Request, response: Response
) -> Envelope[UserView]:
    identity = current_identity(request)
    match = request.headers.get("if-match", "")
    if not re.fullmatch(r'"[0-9]{1,18}"', match):
        raise ApplicationError(
            "PRECONDITION_REQUIRED", "Передайте If-Match из ETag пользователя.", 412
        )
    if int(match[1:-1]) != identity.user.version:
        raise ApplicationError(
            "USER_VERSION_CONFLICT",
            "Настройки уже изменены.",
            409,
            {"current_version": identity.user.version},
        )
    if body.timezone is not None:
        identity.user.timezone = body.timezone
    if body.language is not None:
        identity.user.language_code = body.language
    identity.user.version += 1
    audit(
        current_db(request),
        actor=identity.user.id,
        action="preferences.updated",
        entity_type="user",
        entity_id=identity.user.id,
        request_id=UUID(request.state.request_id),
    )
    response.headers["ETag"] = f'"{identity.user.version}"'
    return Envelope(data=user_view(identity), meta=meta(request))


@router.get("/me/sessions", response_model=Envelope[list[SessionSummary]])
@access("identity.sessions.read")
async def sessions(request: Request) -> Envelope[list[SessionSummary]]:
    identity = current_identity(request)
    now = datetime.now(UTC)
    items = (
        await current_db(request).scalars(
            select(UserSession)
            .where(
                UserSession.user_id == identity.user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.idle_expires_at > now,
            )
            .order_by(UserSession.created_at)
        )
    ).all()
    return Envelope(
        data=[
            SessionSummary(
                id=s.id,
                created_at=s.created_at,
                last_seen_at=s.last_seen_at,
                expires_at=s.expires_at,
                idle_expires_at=s.idle_expires_at,
                current=s.id == identity.session.id,
            )
            for s in items
        ],
        meta=meta(request),
    )


@router.delete("/me/sessions/{session_id}", status_code=204)
@access("identity.sessions.revoke")
async def revoke_session(session_id: UUID, request: Request) -> Response:
    identity = current_identity(request)
    target = await current_db(request).scalar(
        select(UserSession)
        .where(UserSession.id == session_id, UserSession.user_id == identity.user.id)
        .with_for_update()
    )
    if target is None:
        raise ApplicationError("NOT_FOUND", "Сессия не найдена.", 404)
    if target.revoked_at is None:
        target.revoked_at = datetime.now(UTC)
        audit(
            current_db(request),
            actor=identity.user.id,
            action="session.revoked",
            entity_type="session",
            entity_id=target.id,
            request_id=UUID(request.state.request_id),
        )
    response = Response(status_code=204)
    if target.id == identity.session.id:
        clear_cookie(response)
    return response


@router.post("/auth/logout", status_code=204)
@access("public.logout")
async def logout(request: Request) -> Response:
    token = cookie_token(request)
    if token is not None:
        async with identity_transaction(request) as db:
            try:
                identity = await authenticate(
                    db, token, request.app.state.settings, allow_inactive=True
                )
            except ApplicationError as exc:
                if exc.status_code != 401:
                    raise
            else:
                require_csrf(identity, request.headers.get("x-csrf-token"))
                if identity.session.revoked_at is None:
                    identity.session.revoked_at = datetime.now(UTC)
                    audit(
                        db,
                        actor=identity.user.id,
                        action="auth.logout",
                        entity_type="session",
                        entity_id=identity.session.id,
                        request_id=UUID(request.state.request_id),
                    )
    response = Response(status_code=204)
    clear_cookie(response)
    return response
