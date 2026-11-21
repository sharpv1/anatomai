from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
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


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint("mode IN ('learning','exam') AND policy_version=1", name="mode_policy"),
        CheckConstraint("scope IN ('discipline','topic','test')", name="scope"),
        CheckConstraint(
            "(scope='discipline' AND topic_id IS NULL AND test_definition_id IS NULL) "
            "OR (scope='topic' AND topic_id IS NOT NULL AND test_definition_id IS NULL)"
            " OR (scope='test' AND topic_id IS NOT NULL AND test_definition_id IS NOT "
            "NULL)",
            name="scope_fields",
        ),
        CheckConstraint("status IN ('in_progress','completed','abandoned')", name="status"),
        CheckConstraint(
            "total BETWEEN 1 AND 5000 AND current_position>=0 AND "
            "current_position<total AND version>0 AND progress_epoch>=0",
            name="position_version",
        ),
        CheckConstraint(
            "(status='in_progress' AND finalized_at IS NULL AND finish_reason IS NULL) "
            "OR (status<>'in_progress' AND finalized_at>=started_at AND finish_reason "
            "IS NOT NULL)",
            name="final_time",
        ),
        CheckConstraint(
            "(status<>'completed' AND "
            "num_nonnulls(correct,wrong,skipped,answered,percent,duration_seconds)=0) "
            "OR (status='completed' AND "
            "num_nonnulls(correct,wrong,skipped,answered,percent,duration_seconds)=6 "
            "AND correct>=0 AND wrong>=0 AND skipped>=0 AND correct+wrong+skipped=total"
            " AND answered=correct+wrong AND percent BETWEEN 0 AND 100 AND "
            "duration_seconds>=0)",
            name="result",
        ),
        Index(
            "uq_attempts_user_active",
            "user_id",
            unique=True,
            postgresql_where=text("status='in_progress'"),
        ),
        Index("ix_attempts_user_id_id", "user_id", "id"),
        Index(
            "ix_attempts_exam_deadline",
            "deadline_at",
            postgresql_where=text("mode='exam' AND status='in_progress'"),
        ),
        CheckConstraint(
            "(mode='learning' AND deadline_at IS NULL) OR "
            "(mode='exam' AND deadline_at IS NOT NULL AND deadline_at>started_at)",
            name="deadline",
        ),
        ForeignKeyConstraint(
            ["discipline_id", "topic_id"],
            ["topics.discipline_id", "topics.id"],
            name="fk_attempts_topic_discipline",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="RESTRICT"))
    topic_id: Mapped[UUID | None]
    test_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("test_definitions.id", ondelete="RESTRICT")
    )
    scope: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16), default="learning", server_default="learning")
    policy_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    progress_epoch: Mapped[int] = mapped_column(BigInteger)
    timezone_at_start: Mapped[str] = mapped_column(String(64))
    frozen_title: Mapped[str] = mapped_column(String(512))
    catalog_version: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(16), default="in_progress", server_default="in_progress"
    )
    snapshot_ready: Mapped[bool] = mapped_column(default=False, server_default="false")
    total: Mapped[int]
    current_position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    correct: Mapped[int | None]
    wrong: Mapped[int | None]
    skipped: Mapped[int | None]
    answered: Mapped[int | None]
    percent: Mapped[int | None]
    duration_seconds: Mapped[int | None]


class AttemptItem(Base):
    __tablename__ = "attempt_items"
    __table_args__ = (
        UniqueConstraint("attempt_id", "position", name="uq_attempt_items_position"),
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_items_question"),
        UniqueConstraint(
            "id", "attempt_id", "revision_id", name="uq_attempt_items_attempt_revision"
        ),
        UniqueConstraint("id", "revision_id", name="uq_attempt_items_revision"),
        ForeignKeyConstraint(
            ["question_id", "revision_id"],
            ["question_revisions.question_id", "question_revisions.id"],
            name="fk_attempt_items_question_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position BETWEEN 0 AND 4999", name="position"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="RESTRICT"))
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    revision_id: Mapped[UUID]
    position: Mapped[int]


class AttemptOption(Base):
    __tablename__ = "attempt_item_options"
    __table_args__ = (
        UniqueConstraint("item_id", "position", name="uq_attempt_item_options_position"),
        UniqueConstraint(
            "item_id", "revision_id", "option_id", name="uq_attempt_item_options_revision"
        ),
        ForeignKeyConstraint(
            ["item_id", "revision_id"],
            ["attempt_items.id", "attempt_items.revision_id"],
            name="fk_attempt_item_options_item_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["revision_id", "option_id"],
            ["question_options.revision_id", "question_options.id"],
            name="fk_attempt_item_options_content_option",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position BETWEEN 0 AND 7", name="position"),
    )
    item_id: Mapped[UUID] = mapped_column(primary_key=True)
    option_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision_id: Mapped[UUID]
    position: Mapped[int]


class AttemptResponse(Base):
    __tablename__ = "attempt_responses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "attempt_id", "revision_id"],
            ["attempt_items.id", "attempt_items.attempt_id", "attempt_items.revision_id"],
            name="fk_attempt_responses_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["item_id", "revision_id", "selected_option_id"],
            [
                "attempt_item_options.item_id",
                "attempt_item_options.revision_id",
                "attempt_item_options.option_id",
            ],
            name="fk_attempt_responses_selected_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(state='committed' AND selected_option_id IS NOT NULL AND is_correct IS "
            "NOT NULL) OR (state='skipped' AND selected_option_id IS NULL AND "
            "is_correct IS NULL)",
            name="state",
        ),
        Index("ix_attempt_responses_attempt_id", "attempt_id"),
    )
    item_id: Mapped[UUID] = mapped_column(primary_key=True)
    attempt_id: Mapped[UUID]
    revision_id: Mapped[UUID]
    attempt_version: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    state: Mapped[str] = mapped_column(String(16))
    selected_option_id: Mapped[UUID | None]
    is_correct: Mapped[bool | None]
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class AttemptCommand(Base):
    __tablename__ = "attempt_commands"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "operation", "key", name="uq_attempt_commands_actor_operation_key"
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(result)='object' AND "
            "octet_length(result::text)<=1000000",
            name="payload",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="RESTRICT"))
    operation: Mapped[str] = mapped_column(String(64))
    key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class ExamAnswer(Base):
    __tablename__ = "exam_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "attempt_id", "revision_id"],
            ["attempt_items.id", "attempt_items.attempt_id", "attempt_items.revision_id"],
            name="fk_exam_answers_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["item_id", "revision_id", "selected_option_id"],
            [
                "attempt_item_options.item_id",
                "attempt_item_options.revision_id",
                "attempt_item_options.option_id",
            ],
            name="fk_exam_answers_option",
            ondelete="RESTRICT",
        ),
        Index("ix_exam_answers_attempt_id", "attempt_id"),
    )
    item_id: Mapped[UUID] = mapped_column(primary_key=True)
    attempt_id: Mapped[UUID]
    revision_id: Mapped[UUID]
    selected_option_id: Mapped[UUID | None]
    attempt_version: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
