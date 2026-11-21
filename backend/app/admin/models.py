from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MFACredential(Base):
    __tablename__ = "admin_mfa_credentials"
    __table_args__ = (
        CheckConstraint("version > 0 AND last_counter >= -1", name="versions"),
        CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="failures"),
        CheckConstraint("octet_length(encrypted_secret) BETWEEN 100 AND 2048", name="ciphertext"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    encrypted_secret: Mapped[bytes]
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    last_counter: Mapped[int] = mapped_column(BigInteger, default=-1)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecoveryCode(Base):
    __tablename__ = "admin_recovery_codes"
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="uq_admin_recovery_codes_owner_hash"),
        CheckConstraint(
            "octet_length(code_hash) = 32 AND credential_version > 0", name="hash_version"
        ),
        Index("ix_admin_recovery_codes_user_id_used_at", "user_id", "used_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_mfa_credentials.user_id", ondelete="RESTRICT")
    )
    code_hash: Mapped[bytes]
    credential_version: Mapped[int] = mapped_column(BigInteger)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StepUp(Base):
    __tablename__ = "admin_step_ups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["user_sessions.id", "user_sessions.user_id"],
            name="fk_admin_step_ups_session_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "credential_version > 0 AND octet_length(roles_digest) = 32", name="binding"
        ),
        CheckConstraint(
            "expires_at > verified_at AND expires_at <= verified_at + interval '15 minutes'",
            name="freshness",
        ),
        Index("ix_admin_step_ups_user_id_expires_at", "user_id", "expires_at"),
    )
    session_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_mfa_credentials.user_id", ondelete="RESTRICT")
    )
    credential_version: Mapped[int] = mapped_column(BigInteger)
    roles_digest: Mapped[bytes]
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
