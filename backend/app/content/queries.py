from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select

from app.content.models import (
    AccessPolicy,
    Asset,
    Category,
    ContentSource,
    Discipline,
    Note,
    NoteRevision,
    Question,
    QuestionRevision,
    Topic,
    TopicQuestion,
)


def policy_allowed(column: Any) -> Any:
    return or_(
        column.is_(None),
        exists(
            select(AccessPolicy.id).where(
                AccessPolicy.id == column,
                AccessPolicy.status == "published",
                AccessPolicy.requirement == "authenticated",
            )
        ),
    )


def visible_topics() -> Select[Any]:
    return (
        select(
            Topic.id,
            Topic.discipline_id,
            Topic.category_id,
            Topic.slug,
            Topic.title,
            Topic.position,
            Topic.normalized_search_text,
        )
        .join(Discipline, Discipline.id == Topic.discipline_id)
        .outerjoin(
            Category,
            and_(Category.id == Topic.category_id, Category.discipline_id == Topic.discipline_id),
        )
        .where(
            Topic.status == "published",
            Discipline.status == "published",
            or_(Topic.category_id.is_(None), Category.status == "published"),
            policy_allowed(Topic.access_policy_id),
        )
    )


def visible_questions() -> Select[Any]:
    topics = visible_topics().subquery()
    return (
        select(
            Question.id,
            QuestionRevision.id.label("revision_id"),
            QuestionRevision.text,
            QuestionRevision.normalized_search_text,
            TopicQuestion.position,
            TopicQuestion.topic_id,
            topics.c.discipline_id,
        )
        .select_from(TopicQuestion)
        .join(topics, topics.c.id == TopicQuestion.topic_id)
        .join(Question, Question.id == TopicQuestion.question_id)
        .join(
            QuestionRevision,
            and_(
                Question.current_revision_id == QuestionRevision.id,
                QuestionRevision.question_id == Question.id,
            ),
        )
        .join(ContentSource, ContentSource.id == QuestionRevision.source_id)
        .where(
            Question.archived_at.is_(None),
            QuestionRevision.status == "published",
            QuestionRevision.kind == "single_choice",
            ContentSource.status == "published",
        )
    )


def visible_notes() -> Select[Any]:
    topics = visible_topics().subquery()
    return (
        select(
            Note.id,
            Note.discipline_id,
            Note.topic_id,
            Note.position,
            NoteRevision.id.label("revision_id"),
            NoteRevision.title,
            NoteRevision.normalized_search_text,
            NoteRevision.sanitized_body.label("body"),
            NoteRevision.asset_id,
        )
        .join(Discipline, Discipline.id == Note.discipline_id)
        .join(
            NoteRevision,
            and_(Note.current_revision_id == NoteRevision.id, NoteRevision.note_id == Note.id),
        )
        .join(ContentSource, ContentSource.id == NoteRevision.source_id)
        .where(
            Discipline.status == "published",
            Note.status == "published",
            NoteRevision.status == "published",
            ContentSource.status == "published",
            or_(Note.topic_id.is_(None), Note.topic_id.in_(select(topics.c.id))),
            policy_allowed(Note.access_policy_id),
            or_(
                NoteRevision.asset_id.is_(None),
                exists(
                    select(Asset.id).where(
                        Asset.id == NoteRevision.asset_id, Asset.status == "published"
                    )
                ),
            ),
        )
    )


def count_questions_for(column: Any) -> Any:
    q = visible_questions().subquery()
    return select(func.count()).select_from(q).where(q.c.topic_id == column).scalar_subquery()
