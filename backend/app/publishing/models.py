from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PublicationCommand(Base):
    __tablename__ = "publication_commands"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "operation", "key", name="uq_publication_commands_actor_operation_key"
        ),
        CheckConstraint("length(request_hash)=64", name="hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    operation: Mapped[str] = mapped_column(String(128))
    key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicationRun(Base):
    __tablename__ = "publication_runs"
    __table_args__ = (
        UniqueConstraint(
            "import_job_id", "confirmation_hash", name="uq_publication_runs_confirmation"
        ),
        CheckConstraint(
            "status IN ('queued','processing','completed','failed','cancelled')", name="status"
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND selected_count BETWEEN 1 AND 5000", name="attempts"
        ),
        CheckConstraint("length(staging_hash)=64 AND length(confirmation_hash)=64", name="hashes"),
        CheckConstraint(
            "(status='processing')=(lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="lease",
        ),
        Index("ix_publication_runs_status_lease_sequence", "status", "lease_until", "sequence"),
        Index(
            "uq_publication_runs_active_import",
            "import_job_id",
            unique=True,
            postgresql_where=text("status IN ('queued','processing')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    import_job_id: Mapped[UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="RESTRICT"))
    confirmed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    authorized_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL")
    )
    mfa_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmation_hash: Mapped[str] = mapped_column(String(64))
    staging_hash: Mapped[str] = mapped_column(String(64))
    selection_hash: Mapped[str] = mapped_column(String(64))
    selected_count: Mapped[int]
    file_sha256: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[int]
    result_version: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(default=False, server_default="false")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicationItem(Base):
    __tablename__ = "publication_items"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_publication_items_run_position"),
        UniqueConstraint("run_id", "question_id", name="uq_publication_items_run_question"),
        CheckConstraint("position BETWEEN 1 AND 5000", name="position"),
        CheckConstraint("status IN ('pending','published','unchanged','failed')", name="status"),
        Index("ix_publication_items_run_status_position", "run_id", "status", "position"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("publication_runs.id", ondelete="RESTRICT"))
    import_row_id: Mapped[UUID] = mapped_column(ForeignKey("import_rows.id", ondelete="RESTRICT"))
    position: Mapped[int]
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_revisions.id", ondelete="RESTRICT")
    )
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64))
