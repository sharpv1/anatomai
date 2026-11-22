"""Draft-only operations. No review, publication, pointer restoration or file handling."""

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request, Response
from pydantic import BaseModel
from sqlalchemy import Select, delete, exists, func, or_, select, true
from sqlalchemy.exc import IntegrityError

from app.admin.schemas import QuestionBody, QuestionCreate
from app.content.cursors import normalize
from app.content.fingerprints import fingerprint
from app.content.models import (
    CatalogState,
    ContentSource,
    Question,
    QuestionOption,
    QuestionRevision,
)
from app.content.service import ContentReader, not_found, reader, search
from app.core.errors import ApplicationError
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.schemas import Envelope
from app.identity.service import audit

# These are explicit API allowlists, not ORM serialization or client-selectable model names.
FIELDS: dict[str, tuple[str, ...]] = {
    "disciplines": ("id", "slug", "title", "icon_key", "color_token", "position", "status"),
    "topics": ("id", "discipline_id", "category_id", "slug", "title", "position", "status"),
    "test_definitions": (
        "id",
        "topic_id",
        "slug",
        "title",
        "exam_duration_seconds",
        "question_limit",
        "internal_difficulty",
        "status",
    ),
    "content_sources": (
        "id",
        "slug",
        "title",
        "attribution",
        "license_reference",
        "created_by",
        "status",
    ),
}


def can_review(request: Request) -> bool:
    return bool(current_identity(request).roles.intersection({"admin", "content_reviewer"}))


def source_scope(request: Request, statement: Select[Any]) -> Select[Any]:
    if not can_review(request):
        statement = statement.where(
            or_(
                ContentSource.created_by == current_identity(request).user.id,
                ContentSource.status == "published",
            )
        )
    return statement


def revision_visibility(request: Request) -> Any:
    if can_review(request):
        return True
    return or_(
        QuestionRevision.created_by == current_identity(request).user.id,
        QuestionRevision.status != "draft",
    )


def tag(version: int) -> str:
    return f'"content-{version}"'


async def write_guard(request: Request) -> None:
    # Single lock order: identity user -> session -> MFA -> catalog -> content.
    # Statement triggers use this same singleton; even different editors serialize writes.
    state = await current_db(request).get(CatalogState, 1, with_for_update=True)
    if state is None:
        raise ApplicationError("SERVICE_NOT_READY", "Каталог ещё не готов.", 503)
    if request.headers.get("if-match") != tag(state.version):
        raise ApplicationError("PRECONDITION_FAILED", "Обновите карточку перед изменением.", 412)


async def flush(request: Request) -> None:
    try:
        await current_db(request).flush()
    except IntegrityError:
        raise ApplicationError(
            "CONTENT_CONFLICT", "Конфликт идентификатора, связи или позиции.", 409
        ) from None


async def completed(
    request: Request,
    response: Response,
    data: dict[str, Any],
    action: str,
    entity_type: str,
    entity_id: UUID,
) -> Envelope[dict[str, Any]]:
    audit(
        current_db(request),
        actor=current_identity(request).user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=UUID(request.state.request_id),
    )
    await flush(request)
    version = await current_db(request).scalar(
        select(CatalogState.version).where(CatalogState.id == 1)
    )
    assert version is not None
    response.headers["ETag"] = tag(version)
    return Envelope(data=data, meta=meta(request))


def fields(model: Any, item: Any) -> dict[str, Any]:
    return {name: getattr(item, name) for name in FIELDS[model.__tablename__]}


async def catalog_list(
    request: Request, response: Response, model: Any, query: str, limit: int, cursor: str | None
) -> Any:
    r = await reader(request)
    columns = [getattr(model, name) for name in FIELDS[model.__tablename__]]
    sort = getattr(model, "position", None)
    if sort is None:
        from sqlalchemy import literal

        sort = literal(0)
    normalized = (
        func.replace(func.lower(func.normalize(ContentSource.title)), "ё", "е")
        if model is ContentSource
        else model.normalized_search_text
    )
    statement = select(
        *columns,
        normalized.label("normalized_search_text"),
        sort.label("sort_position"),
        model.id.label("sort_id"),
    )
    if model is ContentSource:
        statement = source_scope(request, statement)
    rows, page = await r.rows(
        search(statement, normalized, query),
        scope="admin:" + model.__tablename__,
        filters={
            "query": normalize(query),
            "roles": "|".join(sorted(current_identity(request).roles)),
        },
        limit=limit,
        cursor=cursor,
    )
    data = [{name: row[name] for name in FIELDS[model.__tablename__]} for row in rows]
    result = await r.listing(data, page)
    response.headers["ETag"] = tag(r.version)
    return result


async def catalog_item(
    request: Request, model: Any, entity_id: UUID, *, writing: bool = False
) -> Any:
    statement = select(model).where(model.id == entity_id)
    if model is ContentSource:
        statement = source_scope(request, statement)
    item = await current_db(request).scalar(statement)
    if item is None:
        raise not_found()
    if writing and item.status != "draft":
        raise ApplicationError("DRAFT_REQUIRED", "Изменять можно только черновик.", 409)
    if writing and model is ContentSource and item.created_by != current_identity(request).user.id:
        if "admin" not in current_identity(request).roles:
            raise not_found()
    return item


async def catalog_get(request: Request, response: Response, model: Any, entity_id: UUID) -> Any:
    r = await reader(request)
    item = await catalog_item(request, model, entity_id)
    data = fields(model, item)
    await r.finish()
    response.headers["ETag"] = tag(r.version)
    return Envelope(data=data, meta=meta(request))


async def catalog_save(
    request: Request, response: Response, model: Any, body: BaseModel, entity_id: UUID | None = None
) -> Any:
    await write_guard(request)
    item = (
        await catalog_item(request, model, entity_id, writing=True)
        if entity_id
        else model(id=uuid4(), status="draft")
    )
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    if model is ContentSource:
        item.created_by = current_identity(request).user.id
        item.reviewed_by = None
        item.reviewed_at = None
    current_db(request).add(item)
    await flush(request)
    return await completed(
        request, response, fields(model, item), "content.draft.saved", model.__tablename__, item.id
    )


async def catalog_archive(request: Request, response: Response, model: Any, entity_id: UUID) -> Any:
    await write_guard(request)
    item = await catalog_item(request, model, entity_id, writing=True)
    item.status = "withdrawn"
    await flush(request)
    return await completed(
        request,
        response,
        fields(model, item),
        "content.draft.archived",
        model.__tablename__,
        item.id,
    )


async def allowed_source(request: Request, source_id: UUID | None) -> None:
    if source_id is None:
        return
    source = await catalog_item(request, ContentSource, source_id)
    if source.status == "withdrawn":
        raise not_found()


async def logical_question(request: Request, question_id: UUID) -> Question:
    visible = exists(
        select(QuestionRevision.id).where(
            QuestionRevision.question_id == Question.id, revision_visibility(request)
        )
    )
    question = await current_db(request).scalar(
        select(Question).where(Question.id == question_id, visible)
    )
    if question is None or question.archived_at is not None:
        raise not_found()
    return question


async def revision_item(
    request: Request, revision_id: UUID, *, writing: bool = False
) -> QuestionRevision:
    revision = await current_db(request).scalar(
        select(QuestionRevision).where(
            QuestionRevision.id == revision_id, revision_visibility(request)
        )
    )
    if revision is None:
        raise not_found()
    if writing:
        if revision.status != "draft":
            raise ApplicationError(
                "DRAFT_REQUIRED", "Нужна новая редакция опубликованного вопроса.", 409
            )
        if (
            revision.created_by != current_identity(request).user.id
            and "admin" not in current_identity(request).roles
        ):
            raise not_found()
    return revision


async def revision_data(request: Request, revision: QuestionRevision) -> dict[str, Any]:
    options = (
        await current_db(request).scalars(
            select(QuestionOption)
            .where(QuestionOption.revision_id == revision.id)
            .order_by(QuestionOption.position)
        )
    ).all()
    return {
        "id": revision.id,
        "question_id": revision.question_id,
        "revision_number": revision.revision_number,
        "status": revision.status,
        "kind": revision.kind,
        "text": revision.text,
        "explanation": revision.explanation,
        "source_id": revision.source_id,
        "source_reference": revision.source_reference,
        "source_page": revision.source_page,
        "license_reference": revision.license_reference,
        "created_by": revision.created_by,
        "medical_review_by": revision.medical_review_by,
        "options": [
            {
                "id": option.id,
                "code": option.code,
                "text": option.text,
                "is_correct": option.is_correct,
            }
            for option in options
        ],
    }


async def revision_get(request: Request, response: Response, revision_id: UUID) -> Any:
    r = await reader(request)
    data = await revision_data(request, await revision_item(request, revision_id))
    await r.finish()
    response.headers["ETag"] = tag(r.version)
    return Envelope(data=data, meta=meta(request))


async def save_revision(
    request: Request,
    response: Response,
    body: QuestionBody,
    *,
    question_id: UUID | None = None,
    revision_id: UUID | None = None,
) -> Any:
    await write_guard(request)
    await allowed_source(request, body.source_id)
    db = current_db(request)
    if revision_id is not None:
        revision = await revision_item(request, revision_id, writing=True)
        await db.execute(delete(QuestionOption).where(QuestionOption.revision_id == revision.id))
    else:
        if question_id is None:
            assert isinstance(body, QuestionCreate)
            question = Question(
                id=uuid4(), external_source="medical-admin", external_id=body.external_id
            )
            db.add(question)
            await flush(request)
            question_id = question.id
            number = 1
        else:
            await logical_question(request, question_id)
            number = (
                await db.scalar(
                    select(func.max(QuestionRevision.revision_number)).where(
                        QuestionRevision.question_id == question_id
                    )
                )
                or 0
            ) + 1
        revision = QuestionRevision(id=uuid4(), question_id=question_id, revision_number=number)
        db.add(revision)
    for name in (
        "kind",
        "text",
        "explanation",
        "source_id",
        "source_reference",
        "source_page",
        "license_reference",
    ):
        setattr(revision, name, getattr(body, name))
    revision.created_by = current_identity(request).user.id
    revision.medical_review_by = None
    revision.reviewed_at = None
    revision.status = "draft"
    revision.fingerprint = fingerprint(body)
    await flush(request)
    db.add_all(
        [
            QuestionOption(
                id=uuid4(),
                revision_id=revision.id,
                position=i,
                code=option.code,
                text=option.text,
                is_correct=option.is_correct,
            )
            for i, option in enumerate(body.options)
        ]
    )
    await flush(request)
    return await completed(
        request,
        response,
        await revision_data(request, revision),
        "content.revision.saved",
        "question_revision",
        revision.id,
    )


async def question_get(request: Request, response: Response, question_id: UUID) -> Any:
    r = await reader(request)
    question = await logical_question(request, question_id)
    data = {"id": question.id, "current_revision_id": question.current_revision_id}
    await r.finish()
    response.headers["ETag"] = tag(r.version)
    return Envelope(data=data, meta=meta(request))


async def revision_list(
    request: Request,
    response: Response,
    question_id: UUID | None,
    query: str,
    limit: int,
    cursor: str | None,
) -> Any:
    from sqlalchemy import literal

    r: ContentReader = await reader(request)
    if question_id is not None:
        await logical_question(request, question_id)
    statement: Select[Any] = select(
        QuestionRevision.id,
        QuestionRevision.question_id,
        QuestionRevision.revision_number,
        QuestionRevision.text,
        QuestionRevision.status,
        QuestionRevision.revision_number.label("sort_position"),
        QuestionRevision.id.label("sort_id"),
    ).where(revision_visibility(request))
    if question_id is not None:
        statement = statement.where(QuestionRevision.question_id == question_id)
    else:
        # One latest *visible* revision per question, not an accidental draft disclosure.
        from sqlalchemy.orm import aliased

        other = aliased(QuestionRevision)
        owner = (
            true()
            if can_review(request)
            else or_(other.created_by == current_identity(request).user.id, other.status != "draft")
        )
        statement = statement.where(
            ~exists(
                select(other.id).where(
                    other.question_id == QuestionRevision.question_id,
                    owner,
                    other.revision_number > QuestionRevision.revision_number,
                )
            )
        )
        statement = statement.with_only_columns(
            QuestionRevision.id.label("revision_id"),
            QuestionRevision.question_id.label("id"),
            QuestionRevision.text,
            QuestionRevision.status,
            literal(0).label("sort_position"),
            QuestionRevision.question_id.label("sort_id"),
        )
    rows, page = await r.rows(
        search(statement, QuestionRevision.normalized_search_text, query),
        scope="admin:revisions" if question_id else "admin:questions",
        filters={
            "question": str(question_id),
            "query": normalize(query),
            "roles": "|".join(sorted(current_identity(request).roles)),
        },
        limit=limit,
        cursor=cursor,
    )
    data = [
        {key: value for key, value in row.items() if not key.startswith("sort_")} for row in rows
    ]
    result = await r.listing(data, page)
    response.headers["ETag"] = tag(r.version)
    return result
