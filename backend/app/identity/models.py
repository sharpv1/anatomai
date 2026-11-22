from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("telegram_user_id > 0", name="telegram_id"),
        CheckConstraint("status IN ('active', 'blocked', 'anonymized')", name="status"),
        CheckConstraint("version > 0 AND progress_epoch >= 0", name="versions"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(256), default="")
    last_name: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(64))
    photo_url: Mapped[str | None] = mapped_column(String(2048))
    language_code: Mapped[str] = mapped_column(String(32), default="ru")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(String(16), default="active")
    progress_epoch: Mapped[int] = mapped_column(BigInteger, default=0)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(256))


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_code_user_id", "role_code", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True
    )
    granted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_user_sessions_id_user_id"),
        CheckConstraint(
            "idle_expires_at <= expires_at AND expires_at > created_at "
            "AND idle_expires_at > created_at",
            name="expiry",
        ),
        CheckConstraint(
            "octet_length(token_hash) = 32 AND octet_length(csrf_hash) = 32", name="hashes"
        ),
        Index("ix_user_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    csrf_hash: Mapped[bytes]
    rotation_family_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthReplay(Base):
    __tablename__ = "auth_replays"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["user_sessions.id", "user_sessions.user_id"],
            name="fk_auth_replays_session_owner",
            ondelete="RESTRICT",
        ),
        Index("ix_auth_replays_session_id", "session_id"),
        CheckConstraint("octet_length(init_data_digest) = 32", name="digest"),
        CheckConstraint("bot_id > 0", name="bot_id"),
        Index("ix_auth_replays_valid_until", "valid_until"),
    )
    init_data_digest: Mapped[bytes] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    session_id: Mapped[UUID]
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_actor_id_occurred_at", "actor_id", "occurred_at"),
        Index(
            "ix_audit_events_entity_type_entity_id_occurred_at",
            "entity_type",
            "entity_id",
            "occurred_at",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[UUID]
    request_id: Mapped[UUID]
    safe_diff: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
