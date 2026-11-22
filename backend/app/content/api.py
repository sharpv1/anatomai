import re
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import Select, func, select

from app.content.cursors import normalize
from app.content.models import Asset, Category, Discipline, QuestionOption, TestDefinition
from app.content.queries import (
    count_questions_for,
    visible_notes,
    visible_questions,
    visible_topics,
)
from app.content.schemas import (
    CategoryDTO,
    DisciplineDTO,
    ExamQuestionDTO,
    LearningQuestionDTO,
    Listing,
    NoteDTO,
    NoteSummaryDTO,
    ReferenceQuestionDTO,
    SafeOptionDTO,
    TestDTO,
    TopicDTO,
)
from app.content.service import ContentReader, not_found, reader, search
from app.core.errors import ApplicationError
from app.identity.api import meta
from app.identity.policy import access
from app.identity.schemas import Envelope

router = APIRouter(prefix="/api/v1", tags=["content"])
Limit = Annotated[int, Query(ge=1, le=100)]
QuestionLimit = Annotated[int, Query(ge=1, le=30)]
Cursor = Annotated[str | None, Query(max_length=2048)]
Search = Annotated[str, Query(max_length=200)]


@router.get("/meta", response_model=Envelope[dict[str, Any]])
@access("public.meta")
async def app_metadata(request: Request) -> Envelope[dict[str, Any]]:
    return Envelope(
        data={
            "brand": "MEDEXA",
            "api_version": "1",
            "supported_question_kinds": ["single_choice"],
            "capabilities": {
                "content_configured": request.app.state.settings.content_cursor_signing_key
                is not None,
                "attempts": True,
                "asset_delivery": request.app.state.settings.content_asset_delivery_enabled,
                "billing": False,
            },
        },
        meta=meta(request),
    )


def disciplines_query() -> Select[Any]:
    topics = visible_topics().subquery()
    questions = visible_questions().subquery()
    notes = visible_notes().subquery()
    return select(
        Discipline.id,
        Discipline.slug,
        Discipline.title,
        Discipline.icon_key,
        Discipline.color_token,
        select(func.count(func.distinct(questions.c.id)))
        .where(questions.c.discipline_id == Discipline.id)
        .scalar_subquery()
        .label("question_count"),
        select(func.count())
        .select_from(topics)
        .where(topics.c.discipline_id == Discipline.id)
        .scalar_subquery()
        .label("topic_count"),
        select(func.count())
        .select_from(notes)
        .where(notes.c.discipline_id == Discipline.id)
        .scalar_subquery()
        .label("note_count"),
        Discipline.position.label("sort_position"),
        Discipline.id.label("sort_id"),
        Discipline.normalized_search_text,
    ).where(Discipline.status == "published")


def categories_query() -> Select[Any]:
    topics = visible_topics().subquery()
    return (
        select(
            Category.id,
            Category.discipline_id,
            Category.slug,
            Category.title,
            select(func.count())
            .select_from(topics)
            .where(topics.c.category_id == Category.id)
            .scalar_subquery()
            .label("topic_count"),
            Category.position.label("sort_position"),
            Category.id.label("sort_id"),
            Category.normalized_search_text,
        )
        .join(Discipline, Discipline.id == Category.discipline_id)
        .where(Category.status == "published", Discipline.status == "published")
    )


def topics_query() -> Select[Any]:
    t = visible_topics().subquery()
    definition = (
        select(TestDefinition.id)
        .where(TestDefinition.topic_id == t.c.id, TestDefinition.status == "published")
        .order_by(TestDefinition.id)
        .limit(1)
        .scalar_subquery()
    )
    return select(
        t.c.id,
        t.c.discipline_id,
        t.c.category_id,
        t.c.slug,
        t.c.title,
        t.c.normalized_search_text,
        t.c.position.label("sort_position"),
        t.c.id.label("sort_id"),
        count_questions_for(t.c.id).label("question_count"),
        definition.label("test_definition_id"),
    )


def tests_query() -> Select[Any]:
    topics = visible_topics().subquery()
    count = count_questions_for(TestDefinition.topic_id)
    return (
        select(
            TestDefinition.id,
            TestDefinition.topic_id,
            TestDefinition.slug,
            TestDefinition.title,
            TestDefinition.exam_duration_seconds,
            TestDefinition.normalized_search_text,
            func.least(count, func.coalesce(TestDefinition.question_limit, count)).label(
                "question_count"
            ),
            topics.c.position.label("sort_position"),
            TestDefinition.id.label("sort_id"),
            TestDefinition.question_limit,
            TestDefinition.selection_policy,
            TestDefinition.policy_version,
        )
        .join(topics, topics.c.id == TestDefinition.topic_id)
        .where(TestDefinition.status == "published")
    )


def available_modes(row: Any, *, definition: bool = False) -> list[str]:
    """Catalog capability hint; attempts still authoritatively validate the snapshot."""
    count = row["question_count"]
    if not 1 <= count <= 5000:
        return []
    if not definition:
        return ["learning", "exam"]
    if row["selection_policy"] != "ordered_all" or row["policy_version"] != 1:
        return []
    modes = ["learning"] if row["question_limit"] is None else []
    if 1 <= row["exam_duration_seconds"] <= 86400 and (
        row["question_limit"] is None or row["question_limit"] <= count
    ):
        modes.append("exam")
    return modes


def project[T: BaseModel](model: type[T], row: Any, **extra: Any) -> T:
    # Only explicitly declared DTO fields can leave the service, never the ORM entity.
    if model in (TopicDTO, TestDTO):
        extra["available_modes"] = available_modes(row, definition=model is TestDTO)
    fields = model.model_fields
    return model.model_validate({key: extra[key] if key in extra else row[key] for key in fields})


async def detail[T: BaseModel](
    r: ContentReader,
    statement: Select[Any],
    id_column: Any,
    entity_id: UUID,
    model: type[T],
    **extra: Any,
) -> Envelope[T]:
    row = (await r.db.execute(statement.where(id_column == entity_id))).mappings().one_or_none()
    if row is None:
        raise not_found()
    await r.finish()
    return Envelope(data=project(model, row, **extra), meta=meta(r.request))


@router.get("/disciplines", response_model=Listing[DisciplineDTO])
@access("public.catalog")
async def disciplines(
    request: Request, query: Search = "", limit: Limit = 20, cursor: Cursor = None
) -> Listing[DisciplineDTO]:
    r = await reader(request)
    s = disciplines_query()
    rows, page = await r.rows(
        search(s, s.selected_columns.normalized_search_text, query),
        scope="disciplines",
        filters={"query": normalize(query)},
        limit=limit,
        cursor=cursor,
    )
    return await r.listing([project(DisciplineDTO, row) for row in rows], page)


@router.get("/disciplines/{entity_id}", response_model=Envelope[DisciplineDTO])
@access("public.catalog")
async def discipline(entity_id: UUID, request: Request) -> Envelope[DisciplineDTO]:
    return await detail(
        await reader(request), disciplines_query(), Discipline.id, entity_id, DisciplineDTO
    )


@router.get("/categories", response_model=Listing[CategoryDTO])
@access("public.catalog")
async def categories(
    request: Request,
    discipline_id: UUID | None = None,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Listing[CategoryDTO]:
    r = await reader(request)
    s = categories_query()
    if discipline_id is not None:
        s = s.where(Category.discipline_id == discipline_id)
    rows, page = await r.rows(
        search(s, s.selected_columns.normalized_search_text, query),
        scope="categories",
        filters={"discipline": str(discipline_id), "query": normalize(query)},
        limit=limit,
        cursor=cursor,
    )
    return await r.listing([project(CategoryDTO, row) for row in rows], page)


@router.get("/categories/{entity_id}", response_model=Envelope[CategoryDTO])
@access("public.catalog")
async def category(entity_id: UUID, request: Request) -> Envelope[CategoryDTO]:
    return await detail(
        await reader(request), categories_query(), Category.id, entity_id, CategoryDTO
    )


@router.get("/topics", response_model=Listing[TopicDTO])
@access("public.catalog")
async def topics(
    request: Request,
    discipline_id: UUID | None = None,
    category_id: UUID | None = None,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Listing[TopicDTO]:
    r = await reader(request)
    s = topics_query()
    if discipline_id is not None:
        s = s.where(s.selected_columns.discipline_id == discipline_id)
    if category_id is not None:
        s = s.where(s.selected_columns.category_id == category_id)
    # Search covers both discipline and theme, matching the existing catalog semantics.
    titles = (
        select(Discipline.normalized_search_text)
        .where(Discipline.id == s.selected_columns.discipline_id)
        .scalar_subquery()
    )
    s = search(s, s.selected_columns.normalized_search_text + " " + titles, query)
    rows, page = await r.rows(
        s,
        scope="topics",
        filters={
            "discipline": str(discipline_id),
            "category": str(category_id),
            "query": normalize(query),
        },
        limit=limit,
        cursor=cursor,
    )
    return await r.listing([project(TopicDTO, row) for row in rows], page)


@router.get("/topics/{entity_id}", response_model=Envelope[TopicDTO])
@access("public.catalog")
async def topic(entity_id: UUID, request: Request) -> Envelope[TopicDTO]:
    s = topics_query()
    return await detail(await reader(request), s, s.selected_columns.id, entity_id, TopicDTO)


@router.get("/test-definitions", response_model=Listing[TestDTO])
@access("public.catalog")
async def tests(
    request: Request,
    topic_id: UUID | None = None,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Listing[TestDTO]:
    r = await reader(request)
    s = tests_query()
    if topic_id is not None:
        s = s.where(TestDefinition.topic_id == topic_id)
    rows, page = await r.rows(
        search(s, s.selected_columns.normalized_search_text, query),
        scope="tests",
        filters={"topic": str(topic_id), "query": normalize(query)},
        limit=limit,
        cursor=cursor,
    )
    return await r.listing([project(TestDTO, row) for row in rows], page)


@router.get("/test-definitions/{entity_id}", response_model=Envelope[TestDTO])
@access("public.catalog")
async def test(entity_id: UUID, request: Request) -> Envelope[TestDTO]:
    return await detail(
        await reader(request),
        tests_query(),
        TestDefinition.id,
        entity_id,
        TestDTO,
    )


async def question_page(
    r: ContentReader,
    *,
    topic_id: UUID,
    scope: str,
    query: str,
    limit: int,
    cursor: str | None,
    reference: bool,
    question_limit: int | None = None,
    projection: str = "exam",
) -> Listing[ReferenceQuestionDTO] | Listing[ExamQuestionDTO] | Listing[LearningQuestionDTO]:
    available = visible_topics().subquery()
    if await r.db.scalar(select(available.c.id).where(available.c.id == topic_id)) is None:
        raise not_found()
    base = visible_questions()
    base = base.where(base.selected_columns.topic_id == topic_id)
    ordered = base.add_columns(
        func.row_number()
        .over(order_by=(base.selected_columns.position, base.selected_columns.id))
        .label("number")
    ).subquery()
    s = select(ordered, ordered.c.position.label("sort_position"), ordered.c.id.label("sort_id"))
    if question_limit is not None:
        s = s.where(ordered.c.number <= question_limit)
    rows, page = await r.rows(
        search(s, ordered.c.normalized_search_text, query),
        scope=scope,
        filters={"topic": str(topic_id), "query": normalize(query), "projection": projection},
        limit=limit,
        cursor=cursor,
    )
    revision_ids = [row["revision_id"] for row in rows]
    options = (
        (
            await r.db.execute(
                select(
                    QuestionOption.revision_id,
                    QuestionOption.id,
                    QuestionOption.position,
                    QuestionOption.code,
                    QuestionOption.text,
                )
                .where(QuestionOption.revision_id.in_(revision_ids))
                .order_by(QuestionOption.position)
            )
        )
        .mappings()
        .all()
    )
    by_revision: dict[UUID, list[SafeOptionDTO]] = {rid: [] for rid in revision_ids}
    for option in options:
        by_revision[option["revision_id"]].append(project(SafeOptionDTO, option))
    correct: dict[UUID, list[UUID]] = {rid: [] for rid in revision_ids}
    if reference:
        keys = await r.db.execute(
            select(QuestionOption.revision_id, QuestionOption.id).where(
                QuestionOption.revision_id.in_(revision_ids), QuestionOption.is_correct.is_(True)
            )
        )
        for revision_id, option_id in keys:
            correct[revision_id].append(option_id)
    safe = [
        ExamQuestionDTO(
            question_id=row["id"],
            revision_id=row["revision_id"],
            number=row["number"],
            kind="single_choice",
            text=row["text"],
            options=by_revision[row["revision_id"]],
        )
        for row in rows
    ]
    if reference:
        refs = [
            ReferenceQuestionDTO.model_validate(
                {**item.model_dump(), "correct_option_ids": correct[item.revision_id]}
            )
            for item in safe
        ]
        return await r.listing(refs, page)
    if projection == "learning":
        return await r.listing(
            [LearningQuestionDTO.model_validate(item.model_dump()) for item in safe], page
        )
    return await r.listing(safe, page)


async def guard_exam_reference(request: Request) -> None:
    from app.attempts.exam import expire
    from app.attempts.models import Attempt
    from app.identity.dependencies import current_db, current_identity

    db = current_db(request)
    a = await db.scalar(
        select(Attempt)
        .where(
            Attempt.user_id == current_identity(request).user.id,
            Attempt.mode == "exam",
            Attempt.status == "in_progress",
        )
        .with_for_update()
    )
    if a is not None:
        now = await db.scalar(select(func.clock_timestamp()))
        if now is not None and a.deadline_at is not None and now >= a.deadline_at:
            await expire(db, a)
        else:
            raise ApplicationError(
                "EXAM_REFERENCE_LOCKED", "Разбор доступен после завершения экзамена.", 409
            )


@router.get("/topics/{topic_id}/reference-questions", response_model=Listing[ReferenceQuestionDTO])
@access("content.read")
async def reference(
    topic_id: UUID,
    request: Request,
    query: Search = "",
    limit: QuestionLimit = 30,
    cursor: Cursor = None,
) -> Listing[ReferenceQuestionDTO]:
    await guard_exam_reference(request)
    return cast(
        Listing[ReferenceQuestionDTO],
        await question_page(
            await reader(request),
            topic_id=topic_id,
            scope="reference",
            query=query,
            limit=limit,
            cursor=cursor,
            reference=True,
        ),
    )


@router.get(
    "/test-definitions/{entity_id}/questions",
    response_model=Listing[ExamQuestionDTO] | Listing[LearningQuestionDTO],
)
@access("content.read")
async def safe_questions(
    entity_id: UUID,
    request: Request,
    projection: Literal["exam", "learning"] = "exam",
    query: Search = "",
    limit: QuestionLimit = 30,
    cursor: Cursor = None,
) -> Listing[ExamQuestionDTO] | Listing[LearningQuestionDTO]:
    if projection == "learning":
        await guard_exam_reference(request)
    r = await reader(request)
    s = tests_query()
    definition = (
        (await r.db.execute(s.where(TestDefinition.id == entity_id))).mappings().one_or_none()
    )
    if definition is None:
        raise not_found()
    return cast(
        Listing[ExamQuestionDTO] | Listing[LearningQuestionDTO],
        await question_page(
            r,
            topic_id=definition["topic_id"],
            scope="test:" + str(entity_id),
            query=query,
            limit=limit,
            cursor=cursor,
            reference=False,
            question_limit=definition["question_limit"],
            projection=projection,
        ),
    )


@router.get("/notes", response_model=Listing[NoteSummaryDTO])
@access("content.read")
async def notes(
    request: Request,
    discipline_id: UUID | None = None,
    topic_id: UUID | None = None,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Listing[NoteSummaryDTO]:
    r = await reader(request)
    n = visible_notes().subquery()
    s = select(
        n.c.id,
        n.c.discipline_id,
        n.c.topic_id,
        n.c.title,
        n.c.normalized_search_text,
        n.c.position.label("sort_position"),
        n.c.id.label("sort_id"),
    )
    if discipline_id is not None:
        s = s.where(n.c.discipline_id == discipline_id)
    if topic_id is not None:
        s = s.where(n.c.topic_id == topic_id)
    rows, page = await r.rows(
        search(s, n.c.normalized_search_text, query),
        scope="notes",
        filters={
            "discipline": str(discipline_id),
            "topic": str(topic_id),
            "query": normalize(query),
        },
        limit=limit,
        cursor=cursor,
    )
    return await r.listing([project(NoteSummaryDTO, row) for row in rows], page)


@router.get("/notes/{entity_id}", response_model=Envelope[NoteDTO])
@access("content.read")
async def note(entity_id: UUID, request: Request) -> Envelope[NoteDTO]:
    r = await reader(request)
    n = visible_notes().subquery()
    row = (await r.db.execute(select(n).where(n.c.id == entity_id))).mappings().one_or_none()
    if row is None:
        raise not_found()
    await r.finish()
    return Envelope(
        data=project(
            NoteDTO,
            row,
            body_format="plain_text",
            download_available=bool(
                row["asset_id"] and request.app.state.settings.content_asset_delivery_enabled
            ),
        ),
        meta=meta(request),
    )


@router.get("/assets/{entity_id}/download")
@access("content.read")
async def asset(entity_id: UUID, request: Request) -> Response:
    r = await reader(request)
    n = visible_notes().subquery()
    permitted = (
        (
            await r.db.execute(
                select(Asset.id, Asset.storage_key).where(
                    Asset.id == entity_id,
                    Asset.status == "published",
                    Asset.id.in_(select(n.c.asset_id)),
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if permitted is None:
        raise not_found()
    await r.finish()
    if not request.app.state.settings.content_asset_delivery_enabled:
        raise ApplicationError(
            "ASSET_DELIVERY_NOT_CONFIGURED", "Выдача файлов ещё не настроена.", 503
        )
    # Content-addressed keys only: no traversal, encoded separators, header injection or URLs.
    key = permitted["storage_key"]
    if not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{64}(?:\.[a-z0-9]{1,10})?", key):
        raise ApplicationError("ASSET_NOT_READY", "Файл временно недоступен.", 503)
    return Response(
        headers={
            "X-Accel-Redirect": "/internal/medexa-content/" + key,
            "Content-Disposition": f'attachment; filename="{entity_id}"',
            "Content-Type": "application/octet-stream",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
    )
