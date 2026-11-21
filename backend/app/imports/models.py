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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        UniqueConstraint(
            "created_by",
            "sha256",
            "file_format",
            "template_version",
            name="uq_import_jobs_actor_file",
        ),
        CheckConstraint("file_format IN ('xlsx','docx') AND template_version=1", name="format"),
        CheckConstraint(
            "status IN ('queued','processing','completed','failed','cancelled')", name="status"
        ),
        CheckConstraint("phase IN ('queued','parsing','staging','applying','done')", name="phase"),
        CheckConstraint("attempts BETWEEN 0 AND 3 AND result_version>0", name="attempts"),
        CheckConstraint(
            "found BETWEEN 0 AND 5000 AND valid_count>=0 AND error_count>=0 "
            "AND duplicate_count>=0 AND applied_count>=0",
            name="counts",
        ),
        CheckConstraint("octet_length(sha256)=64", name="digest"),
        CheckConstraint(
            "(status='processing')=(lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="lease",
        ),
        Index("ix_import_jobs_status_lease_until_sequence", "status", "lease_until", "sequence"),
        Index("ix_import_jobs_created_by_sequence", "created_by", "sequence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    authorized_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL")
    )
    mfa_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    file_format: Mapped[str] = mapped_column(String(8))
    template_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    phase: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    result_version: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    cancel_requested: Mapped[bool] = mapped_column(default=False, server_default="false")
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    applied_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    raw_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("import_job_id", "position", name="uq_import_rows_job_position"),
        CheckConstraint("position BETWEEN 1 AND 5000", name="position"),
        CheckConstraint(
            "action IN ('pending','create','update','unchanged','duplicate','conflict','error')",
            name="action",
        ),
        CheckConstraint("octet_length(normalized_payload::text)<=65536", name="payload_size"),
        Index("ix_import_rows_import_job_id_position", "import_job_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(64))
    discipline: Mapped[str] = mapped_column(String(512))
    topic: Mapped[str] = mapped_column(String(512))
    external_key: Mapped[str] = mapped_column(String(128))
    generated_key: Mapped[bool]
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    normalized_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    errors: Mapped[list[JsonValue]] = mapped_column(JSONB)
    warnings: Mapped[list[JsonValue]] = mapped_column(JSONB)
    action: Mapped[str] = mapped_column(String(16), default="pending")
    topic_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"))
    target_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT")
    )
    applied_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("question_revisions.id", ondelete="RESTRICT")
    )


class ImportContentKey(Base):
    __tablename__ = "import_content_keys"
    __table_args__ = (CheckConstraint("length(content_hash)=64", name="hash"),)
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), primary_key=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
