from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS = "status IN ('draft', 'published', 'withdrawn')"


class Discipline(Base):
    __tablename__ = "disciplines"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("color_token IN ('blue','mint','violet','orange')", name="color"),
        Index("ix_disciplines_status_position_id", "status", "position", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    icon_key: Mapped[str] = mapped_column(String(64))
    color_token: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("position >= 0", name="position"),
        UniqueConstraint("discipline_id", "slug", name="uq_categories_discipline_slug"),
        UniqueConstraint("discipline_id", "id", name="uq_categories_discipline_id"),
        Index(
            "ix_categories_discipline_id_status_position_id",
            "discipline_id",
            "status",
            "position",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="RESTRICT"))
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class AccessPolicy(Base):
    __tablename__ = "access_policies"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("requirement IN ('authenticated','unavailable')", name="requirement"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    requirement: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("position >= 0", name="position"),
        UniqueConstraint("discipline_id", "slug", name="uq_topics_discipline_slug"),
        UniqueConstraint("discipline_id", "id", name="uq_topics_discipline_id"),
        ForeignKeyConstraint(
            ["discipline_id", "category_id"],
            ["categories.discipline_id", "categories.id"],
            name="fk_topics_category_owner",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_topics_discipline_id_status_position_id",
            "discipline_id",
            "status",
            "position",
            "id",
        ),
        Index("ix_topics_category_id", "category_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="RESTRICT"))
    category_id: Mapped[UUID | None]
    access_policy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("access_policies.id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class TestDefinition(Base):
    __tablename__ = "test_definitions"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        UniqueConstraint("topic_id", "slug"),
        CheckConstraint(
            "exam_duration_seconds > 0 AND (question_limit IS NULL OR question_limit > 0)",
            name="limits",
        ),
        CheckConstraint("selection_policy = 'ordered_all' AND policy_version > 0", name="policy"),
        Index("ix_test_definitions_topic_id_status_id", "topic_id", "status", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    topic_id: Mapped[UUID] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"))
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    exam_duration_seconds: Mapped[int]
    question_limit: Mapped[int | None]
    selection_policy: Mapped[str] = mapped_column(String(32), server_default="ordered_all")
    policy_version: Mapped[int] = mapped_column(Integer, server_default="1")
    internal_difficulty: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("byte_size > 0", name="size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="hash"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    storage_key: Mapped[str] = mapped_column(String(256), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ContentSource(Base):
    __tablename__ = "content_sources"
    __table_args__ = (CheckConstraint(STATUS, name="status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    attribution: Mapped[str] = mapped_column(Text)
    license_reference: Mapped[str | None] = mapped_column(Text)
    evidence_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("external_source", "external_id"),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["question_revisions.question_id", "question_revisions.id"],
            name="fk_questions_current_revision_owner",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_source: Mapped[str] = mapped_column(String(128))
    external_id: Mapped[str | None] = mapped_column(String(128))
    current_revision_id: Mapped[UUID | None]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionRevision(Base):
    __tablename__ = "question_revisions"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        UniqueConstraint(
            "question_id", "revision_number", name="uq_question_revisions_owner_number"
        ),
        UniqueConstraint("question_id", "id", name="uq_question_revisions_owner_id"),
        CheckConstraint(
            "revision_number > 0 AND kind IN ('single_choice','multiple_choice')",
            name="kind_version",
        ),
        CheckConstraint("octet_length(text) BETWEEN 1 AND 8000", name="text_size"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        Index("ix_question_revisions_question_id_status", "question_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    revision_number: Mapped[int]
    kind: Mapped[str] = mapped_column(String(32), server_default="single_choice")
    text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_sources.id", ondelete="RESTRICT")
    )
    license_reference: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text().evaluates_none(), server_default="")
    source_page: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    medical_review_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    fingerprint: Mapped[str] = mapped_column(String(64))


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("revision_id", "id", name="uq_question_options_revision_id"),
        UniqueConstraint("revision_id", "position", name="uq_question_options_revision_position"),
        UniqueConstraint("revision_id", "code", name="uq_question_options_revision_code"),
        CheckConstraint(
            "position >= 0 AND octet_length(text) BETWEEN 1 AND 2000", name="size_position"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_revisions.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    code: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))


class TopicQuestion(Base):
    __tablename__ = "topic_questions"
    __table_args__ = (
        UniqueConstraint("topic_id", "position"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_topic_questions_question_id", "question_id"),
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int]


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        CheckConstraint("position >= 0", name="position"),
        UniqueConstraint("discipline_id", "slug"),
        ForeignKeyConstraint(
            ["discipline_id", "topic_id"],
            ["topics.discipline_id", "topics.id"],
            name="fk_notes_topic_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["note_revisions.note_id", "note_revisions.id"],
            name="fk_notes_current_revision_owner",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_notes_discipline_id_status_position_id", "discipline_id", "status", "position", "id"
        ),
        Index("ix_notes_topic_id", "topic_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="RESTRICT"))
    topic_id: Mapped[UUID | None]
    current_revision_id: Mapped[UUID | None]
    access_policy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("access_policies.id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class NoteRevision(Base):
    __tablename__ = "note_revisions"
    __table_args__ = (
        CheckConstraint(STATUS, name="status"),
        UniqueConstraint("note_id", "revision_number", name="uq_note_revisions_owner_number"),
        UniqueConstraint("note_id", "id", name="uq_note_revisions_owner_id"),
        CheckConstraint(
            "revision_number > 0 AND (sanitized_body IS NOT NULL OR asset_id IS NOT NULL)",
            name="content_version",
        ),
        CheckConstraint(
            "sanitized_body IS NULL OR octet_length(sanitized_body) BETWEEN 1 AND 256000",
            name="body_size",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    revision_number: Mapped[int]
    title: Mapped[str] = mapped_column(String(512))
    normalized_search_text: Mapped[str] = mapped_column(Text, server_default="")
    sanitized_body: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_sources.id", ondelete="RESTRICT")
    )
    source_reference: Mapped[str] = mapped_column(Text, server_default="")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    medical_review_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")


class LegacyMapping(Base):
    __tablename__ = "legacy_mappings"
    __table_args__ = (
        CheckConstraint(
            "(entity_type = 'discipline' AND discipline_id IS NOT NULL AND topic_id IS NULL "
            "AND test_definition_id IS NULL AND question_id IS NULL) OR "
            "(entity_type = 'topic' AND topic_id IS NOT NULL AND discipline_id IS NULL "
            "AND test_definition_id IS NULL AND question_id IS NULL) OR "
            "(entity_type = 'test_definition' AND test_definition_id IS NOT NULL "
            "AND discipline_id IS NULL AND topic_id IS NULL AND question_id IS NULL) OR "
            "(entity_type = 'question' AND question_id IS NOT NULL AND discipline_id IS NULL "
            "AND topic_id IS NULL AND test_definition_id IS NULL)",
            name="typed_target",
        ),
    )
    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    legacy_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    discipline_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="RESTRICT"), unique=True
    )
    topic_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), unique=True
    )
    test_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("test_definitions.id", ondelete="RESTRICT"), unique=True
    )
    question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), unique=True
    )


class CatalogState(Base):
    __tablename__ = "catalog_state"
    __table_args__ = (CheckConstraint("id = 1 AND version > 0", name="singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, server_default="1")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
