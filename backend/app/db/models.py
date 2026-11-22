from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyRequest(Base):
    __tablename__ = "idempotency_requests"
    __table_args__ = (
        UniqueConstraint("actor_id", "operation", "key", name="uq_idempotency_scope_key"),
        CheckConstraint("outcome IN ('processing', 'completed')", name="outcome"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="hash"),
        CheckConstraint("expires_at > created_at", name="expiry"),
        CheckConstraint(
            "(outcome = 'processing' AND response_status IS NULL AND response_projection IS NULL) "
            "OR (outcome = 'completed' AND response_status IS NOT NULL "
            "AND response_status BETWEEN 200 AND 299 "
            "AND response_projection IS NOT NULL AND jsonb_typeof(response_projection) = 'object')",
            name="response",
        ),
        Index("ix_idempotency_requests_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    operation: Mapped[str] = mapped_column(String(128))
    key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[UUID | None]
    outcome: Mapped[str] = mapped_column(String(16))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_projection: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
