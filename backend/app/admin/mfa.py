"""RFC 6238 TOTP, encrypted provisioning and session-bound server-side step-up."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import MFACredential, RecoveryCode, StepUp
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.identity.models import User, UserRole, UserSession
from app.identity.service import Identity, audit

MFA_ROLES = frozenset({"content_editor", "content_reviewer", "billing_admin", "admin"})


def utcnow() -> datetime:
    return datetime.now(UTC)


def cipher(settings: Settings) -> Fernet:
    key = settings.mfa_encryption_key
    if key is None:
        raise ApplicationError("MFA_NOT_CONFIGURED", "MFA ещё не настроена.", 503)
    return Fernet(key.get_secret_value().encode("ascii"))


def validate_secret(secret: str) -> bytes:
    if not re.fullmatch(r"[A-Z2-7]{32}", secret):
        raise ApplicationError(
            "MFA_SECRET_INVALID", "Нужен отдельный 160-bit Base32 TOTP secret.", 422
        )
    return base64.b32decode(secret)


def totp(secret: str, counter: int) -> str:
    digest = hmac.digest(validate_secret(secret), struct.pack(">Q", counter), "sha1")
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1000000:06d}"


def match_counter(secret: str, code: str, now: datetime, last_counter: int) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    current = int(now.timestamp()) // 30
    matches = [
        counter
        for counter in range(max(0, current - 1), current + 2)
        if hmac.compare_digest(totp(secret, counter), code) and counter > last_counter
    ]
    return max(matches) if matches else None


def encrypt_secret(settings: Settings, user_id: UUID, secret: str) -> bytes:
    validate_secret(secret)
    body = json.dumps({"user_id": str(user_id), "secret": secret}, separators=(",", ":")).encode()
    return cipher(settings).encrypt(body)


def decrypt_secret(settings: Settings, user_id: UUID, encrypted: bytes) -> str:
    try:
        body = json.loads(cipher(settings).decrypt(encrypted))
        if body["user_id"] != str(user_id) or not isinstance(body["secret"], str):
            raise ValueError
        secret: str = body["secret"]
        validate_secret(secret)
        return secret
    except (InvalidToken, ValueError, TypeError, KeyError, UnicodeError, ApplicationError) as exc:
        if isinstance(exc, ApplicationError) and exc.code == "MFA_NOT_CONFIGURED":
            raise
        raise ApplicationError("MFA_UNAVAILABLE", "MFA временно недоступна.", 503) from None


def roles_digest(roles: set[str]) -> bytes:
    return hashlib.sha256("\n".join(sorted(roles)).encode()).digest()


def recovery_hash(user_id: UUID, code: str) -> bytes:
    return hashlib.sha256(b"medexa-recovery-v1\0" + user_id.bytes + code.encode()).digest()


async def provision(
    db: AsyncSession,
    settings: Settings,
    telegram_id: int,
    secret: str,
    proof: str,
    *,
    recovery: str | None = None,
) -> list[str]:
    """Operator-only enrollment/recovery. Caller commits before displaying new codes."""
    encrypted: bytes
    user = await db.scalar(
        select(User).where(User.telegram_user_id == telegram_id).with_for_update()
    )
    if user is None or user.status != "active":
        raise ApplicationError("MFA_USER_REQUIRED", "Нужен проверенный активный пользователь.", 409)
    roles = set(
        (await db.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))).all()
    )
    if not roles.intersection(MFA_ROLES):
        raise ApplicationError("ACCESS_DENIED", "Нет административной роли.", 403)
    now = utcnow()
    counter = match_counter(secret, proof, now, -1)
    if counter is None:
        raise ApplicationError("MFA_INVALID", "Код MFA не подтверждён.", 403)
    encrypted = encrypt_secret(settings, user.id, secret)
    credential = await db.get(MFACredential, user.id, with_for_update=True)
    if credential is not None:
        if recovery is None:
            raise ApplicationError(
                "MFA_ALREADY_ENROLLED", "Требуется операторское восстановление.", 409
            )
        code = await db.scalar(
            select(RecoveryCode)
            .where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.credential_version == credential.version,
                RecoveryCode.code_hash == recovery_hash(user.id, recovery),
                RecoveryCode.used_at.is_(None),
            )
            .with_for_update()
        )
        if code is None:
            raise ApplicationError("RECOVERY_INVALID", "Код восстановления недействителен.", 403)
        await db.execute(
            update(RecoveryCode)
            .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
            .values(used_at=now)
        )
        credential.version += 1
        credential.encrypted_secret = encrypted
        credential.last_counter = counter
        credential.failed_attempts = 0
        credential.locked_until = None
        credential.enrolled_at = now
    else:
        if recovery is not None:
            raise ApplicationError("RECOVERY_INVALID", "MFA ещё не зарегистрирована.", 403)
        credential = MFACredential(
            user_id=user.id, encrypted_secret=encrypted, version=1, last_counter=counter
        )
        db.add(credential)
    await db.flush()
    codes = [secrets.token_hex(16) for _ in range(10)]
    db.add_all(
        [
            RecoveryCode(
                user_id=user.id,
                code_hash=recovery_hash(user.id, code),
                credential_version=credential.version,
            )
            for code in codes
        ]
    )
    # Same user -> sessions lock order as login/authenticate/bootstrap.
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(
        update(StepUp)
        .where(StepUp.user_id == user.id, StepUp.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    audit(
        db,
        actor=None,
        action="mfa.recovered" if recovery is not None else "mfa.enrolled",
        entity_type="user",
        entity_id=user.id,
        request_id=uuid4(),
    )
    return codes


async def verify_step_up(
    db: AsyncSession,
    settings: Settings,
    identity: Identity,
    code: str,
    request_id: UUID,
) -> tuple[StepUp | None, ApplicationError | None]:
    """Failures are returned, not raised, so attempts/audit commit before the HTTP error."""
    cipher(settings)
    credential = await db.get(MFACredential, identity.user.id, with_for_update=True)
    if credential is None:
        return None, ApplicationError(
            "MFA_NOT_ENROLLED", "Нужно операторское подключение MFA.", 403
        )
    now = utcnow()
    if credential.locked_until is not None and credential.locked_until > now:
        return None, ApplicationError("MFA_RATE_LIMITED", "Повторите подтверждение MFA позже.", 429)
    if credential.locked_until is not None:
        credential.locked_until = None
        credential.failed_attempts = 0
    secret = decrypt_secret(settings, identity.user.id, credential.encrypted_secret)
    counter = match_counter(secret, code, now, credential.last_counter)
    if counter is None:
        credential.failed_attempts += 1
        if credential.failed_attempts >= 5:
            credential.locked_until = now + timedelta(minutes=5)
        audit(
            db,
            actor=identity.user.id,
            action="mfa.rejected",
            entity_type="user",
            entity_id=identity.user.id,
            request_id=request_id,
        )
        return None, ApplicationError("MFA_INVALID", "Код MFA не подтверждён.", 403)
    credential.last_counter = counter
    credential.failed_attempts = 0
    grant = await db.get(StepUp, identity.session.id, with_for_update=True)
    if grant is None:
        grant = StepUp(session_id=identity.session.id, user_id=identity.user.id)
        db.add(grant)
    grant.credential_version = credential.version
    grant.roles_digest = roles_digest(identity.roles)
    grant.verified_at = now
    grant.expires_at = min(
        now + timedelta(minutes=15), identity.session.expires_at, identity.session.idle_expires_at
    )
    grant.revoked_at = None
    audit(
        db,
        actor=identity.user.id,
        action="mfa.confirmed",
        entity_type="session",
        entity_id=identity.session.id,
        request_id=request_id,
    )
    await db.flush()
    return grant, None


async def require_step_up(db: AsyncSession, identity: Identity, settings: Settings) -> None:
    credential = await db.get(MFACredential, identity.user.id, with_for_update=True)
    grant = await db.get(StepUp, identity.session.id, with_for_update=True)
    now = utcnow()
    if (
        credential is None
        or grant is None
        or grant.user_id != identity.user.id
        or grant.revoked_at is not None
        or grant.expires_at <= now
        or grant.verified_at > now
        or grant.verified_at < now - timedelta(minutes=15)
        or grant.credential_version != credential.version
        or not hmac.compare_digest(grant.roles_digest, roles_digest(identity.roles))
    ):
        raise ApplicationError("MFA_REQUIRED", "Требуется свежее подтверждение MFA.", 403)

    cipher(settings)
