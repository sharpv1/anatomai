import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import JsonValue, SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.identity.models import AuditEvent, AuthReplay, User, UserRole, UserSession
from app.identity.security import csrf_token, token_hash
from app.identity.telegram import TelegramProof


def auth_configuration(settings: Settings) -> tuple[str, str]:
    if settings.telegram_bot_token is None or settings.csrf_signing_key is None:
        raise ApplicationError("AUTH_NOT_CONFIGURED", "Авторизация ещё не настроена.", 503)
    return (
        settings.telegram_bot_token.get_secret_value(),
        settings.csrf_signing_key.get_secret_value(),
    )


def audit(
    db: AsyncSession,
    *,
    actor: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    request_id: UUID,
    details: dict[str, JsonValue] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            safe_diff=details or {},
        )
    )


@dataclass(repr=False)
class Identity:
    user: User
    session: UserSession
    roles: set[str]
    token: SecretStr
    csrf: SecretStr


async def authenticate(
    db: AsyncSession, token: str | None, settings: Settings, *, allow_inactive: bool = False
) -> Identity:
    _, key = auth_configuration(settings)
    if token is None:
        raise ApplicationError("AUTH_REQUIRED", "Войдите через Telegram.", 401)
    candidate = await db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(token))
    )
    if candidate is None:
        raise ApplicationError("AUTH_REQUIRED", "Сессия не подтверждена.", 401)
    # Always user -> session, also for revocation/login/bootstrap.
    user = (
        await db.scalars(select(User).where(User.id == candidate.user_id).with_for_update())
    ).one()
    session = (
        await db.scalars(
            select(UserSession)
            .where(UserSession.id == candidate.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    now = datetime.now(UTC)
    if not allow_inactive:
        if user.status != "active":
            raise ApplicationError("USER_BLOCKED", "Аккаунт недоступен.", 403)
        if (
            session.revoked_at is not None
            or session.expires_at <= now
            or session.idle_expires_at <= now
        ):
            raise ApplicationError("SESSION_EXPIRED", "Откройте Mini App заново.", 401)
    csrf = csrf_token(key, session.id, token)
    if not hmac.compare_digest(token_hash(csrf), session.csrf_hash):
        raise ApplicationError("SESSION_EXPIRED", "Сессия больше не действительна.", 401)
    roles = set(
        (await db.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))).all()
    )
    if not allow_inactive and (now - session.last_seen_at).total_seconds() >= 300:
        session.last_seen_at = now
        session.idle_expires_at = min(
            session.expires_at, now + timedelta(seconds=settings.session_idle_seconds)
        )
    return Identity(user, session, roles, SecretStr(token), SecretStr(csrf))


def require_csrf(identity: Identity, supplied: str | None) -> None:
    if (
        supplied is None
        or not re.fullmatch(r"[0-9a-f]{64}", supplied)
        or not hmac.compare_digest(supplied, identity.csrf.get_secret_value())
    ):
        raise ApplicationError("CSRF_INVALID", "Проверка безопасности запроса не пройдена.", 403)


async def login(
    db: AsyncSession,
    proof: TelegramProof,
    token: str | None,
    settings: Settings,
    *,
    timezone: str | None,
    language: str | None,
    request_id: UUID,
) -> tuple[Identity, bool]:
    _, key = auth_configuration(settings)
    now = datetime.now(UTC)
    # Serializes first-user upsert and canonical replay insertion without a fake identity.
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": proof.user.id})
    user = await db.scalar(
        select(User).where(User.telegram_user_id == proof.user.id).with_for_update()
    )
    current: Identity | None = None
    if token:
        existing = await db.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash(token))
        )
        if (
            existing is not None
            and existing.revoked_at is None
            and min(existing.expires_at, existing.idle_expires_at) > now
        ):
            if user is None or existing.user_id != user.id:
                raise ApplicationError(
                    "SESSION_IDENTITY_MISMATCH", "Сначала выйдите из текущего аккаунта.", 409
                )
            try:
                current = await authenticate(db, token, settings)
            except ApplicationError as exc:
                if exc.code != "SESSION_EXPIRED":
                    raise
                # A fresh verified proof may recover after a CSRF-key rotation;
                # it must never resurrect the old credential.
                existing.revoked_at = now
                audit(
                    db,
                    actor=user.id,
                    action="session.invalidated",
                    entity_type="session",
                    entity_id=existing.id,
                    request_id=request_id,
                )
    if user is not None and user.status != "active":
        raise ApplicationError("USER_BLOCKED", "Аккаунт недоступен.", 403)
    replay = await db.get(AuthReplay, proof.digest)
    if replay is not None:
        if current is not None and replay.user_id == current.user.id:
            return current, False
        raise ApplicationError("AUTH_RELAUNCH_REQUIRED", "Откройте Mini App заново.", 409)
    if user is None:
        user = User(
            id=uuid4(),
            telegram_user_id=proof.user.id,
            first_name=proof.user.first_name,
            timezone=timezone or "UTC",
            language_code=language or proof.user.language_code or "ru",
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_code="student"))
    else:
        user.first_name = proof.user.first_name
        user.version += 1
    user.last_name, user.username, user.photo_url = (
        proof.user.last_name,
        proof.user.username,
        proof.user.photo_url,
    )
    if current is not None:
        current.session.revoked_at = now
        audit(
            db,
            actor=user.id,
            action="session.rotated",
            entity_type="session",
            entity_id=current.session.id,
            request_id=request_id,
        )
    active = (
        await db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.idle_expires_at > now,
            )
            .order_by(UserSession.created_at)
        )
    ).all()
    for old in active[: max(0, len(active) - 9)]:
        old.revoked_at = now
        audit(
            db,
            actor=user.id,
            action="session.evicted",
            entity_type="session",
            entity_id=old.id,
            request_id=request_id,
        )
    raw = secrets.token_urlsafe(32)
    session_id = uuid4()
    csrf = csrf_token(key, session_id, raw)
    expires = now + timedelta(seconds=settings.session_absolute_seconds)
    session = UserSession(
        id=session_id,
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_hash=token_hash(csrf),
        rotation_family_id=current.session.rotation_family_id if current else uuid4(),
        created_at=now,
        last_seen_at=now,
        expires_at=expires,
        idle_expires_at=min(expires, now + timedelta(seconds=settings.session_idle_seconds)),
    )
    db.add(session)
    await db.flush()
    db.add(
        AuthReplay(
            init_data_digest=proof.digest,
            bot_id=proof.bot_id,
            user_id=user.id,
            session_id=session_id,
            valid_until=proof.valid_until,
        )
    )
    audit(
        db,
        actor=user.id,
        action="auth.login",
        entity_type="session",
        entity_id=session_id,
        request_id=request_id,
    )
    roles = set(
        (await db.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))).all()
    )
    return Identity(user, session, roles, SecretStr(raw), SecretStr(csrf)), True
