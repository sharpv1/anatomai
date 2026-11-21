from datetime import date, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.attempts.exam import expire
from app.attempts.models import Attempt
from app.attempts.service import view
from app.content.cursors import decode_cursor, encode_cursor
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.policy import access
from app.identity.schemas import Envelope
from app.progress import service as svc
from app.progress.schemas import (
    Achievement,
    Activity,
    DailyTopic,
    GroupProgress,
    HistoryItem,
    Home,
    Listing,
    Progress,
    Recommendation,
    ResultPage,
    Summary,
    TopicSummary,
)

router = APIRouter(prefix="/api/v1", tags=["personal progress"])
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=2048)]


@router.get("/me/attempts", response_model=Listing[HistoryItem])
@access("progress.self")
async def history(
    request: Request,
    mode: Literal["learning", "exam"] | None = None,
    discipline_id: UUID | None = None,
    topic_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Any:
    rows, page = await svc.history(
        request,
        mode=mode,
        discipline_id=discipline_id,
        topic_id=topic_id,
        start=start,
        end=end,
        cursor=cursor,
        limit=limit,
    )
    return Listing(data=rows, page=page, meta=meta(request))


@router.get("/me/statistics", response_model=Envelope[Summary])
@access("progress.self")
async def statistics(request: Request, period: svc.Period = "all") -> Any:
    return Envelope(data=await svc.summary(request, period), meta=meta(request))


@router.get("/me/activity", response_model=Envelope[Activity])
@access("progress.self")
async def activity(request: Request, week_start: date | None = None) -> Any:
    today = svc.day_in_zone(
        await svc.clock(current_db(request)), current_identity(request).user.timezone
    )
    start = week_start or today - timedelta(days=today.weekday())
    if start.weekday() != 0:
        raise svc.fail("INVALID_WEEK", "Начало недели должно быть понедельником.")
    return Envelope(
        data=await svc.activity(request, start, start + timedelta(days=6)), meta=meta(request)
    )


@router.get("/me/calendar", response_model=Envelope[Activity])
@router.get("/me/result-trends", response_model=Envelope[Activity])
@access("progress.self")
async def calendar(request: Request, start: date, end: date) -> Any:
    return Envelope(data=await svc.activity(request, start, end), meta=meta(request))


@router.get("/me/progress", response_model=Envelope[Progress])
@access("progress.self")
async def progress(request: Request) -> Any:
    return Envelope(
        data={
            "statistics": await svc.summary(request),
            "unattributed_topic_responses": await svc.unattributed(request),
        },
        meta=meta(request),
    )


async def group_page(
    request: Request,
    dimension: Literal["discipline_id", "topic_id"],
    cursor: str | None,
    limit: int,
    discipline_id: UUID | None = None,
) -> Any:
    scope = svc.cursor_scope(
        request, dimension, {"discipline_id": str(discipline_id) if discipline_id else None}
    )
    after = None
    if cursor:
        _, entity = decode_cursor(cursor, svc.cursor_key(request), version=1, scope=scope)
        after = UUID(entity)
    rows = await svc.groups(
        request, dimension, after=after, limit=limit + 1, discipline_id=discipline_id
    )
    more = len(rows) > limit
    rows = rows[:limit]
    token = (
        encode_cursor(
            svc.cursor_key(request),
            version=1,
            scope=scope,
            position=0,
            entity_id=str(rows[-1]["id"]),
        )
        if more
        else None
    )
    return Listing(data=rows, page={"has_more": more, "next_cursor": token}, meta=meta(request))


@router.get("/me/progress/disciplines", response_model=Listing[GroupProgress])
@access("progress.self")
async def disciplines(request: Request, cursor: Cursor = None, limit: Limit = 30) -> Any:
    return await group_page(request, "discipline_id", cursor, limit)


@router.get("/me/progress/topics", response_model=Listing[GroupProgress])
@access("progress.self")
async def topics(
    request: Request, discipline_id: UUID | None = None, cursor: Cursor = None, limit: Limit = 30
) -> Any:
    return await group_page(request, "topic_id", cursor, limit, discipline_id)


@router.get("/me/mistakes", response_model=Listing[GroupProgress])
@access("progress.self")
async def mistakes(
    request: Request,
    group_by: Literal["discipline", "topic"] = "topic",
    cursor: Cursor = None,
    limit: Limit = 30,
) -> Any:
    return await group_page(
        request, "discipline_id" if group_by == "discipline" else "topic_id", cursor, limit
    )


@router.get("/me/topics/{topic_id}/summary", response_model=Envelope[TopicSummary])
@access("progress.self")
async def topic_summary(topic_id: UUID, request: Request) -> Any:
    rows = await svc.groups(request, "topic_id", only=topic_id, limit=1)
    if not rows:
        # Do not disclose unpublished metadata to a student without history.
        from app.content.models import Topic
        from app.content.queries import visible_topics

        visible = await current_db(request).scalar(visible_topics().where(Topic.id == topic_id))
        if visible is None:
            raise svc.fail("NOT_FOUND", "Тема не найдена.", 404)
    row = rows[0] if rows else {}
    return Envelope(
        data={
            "topic_id": topic_id,
            "completed_count": row.get("completed_tests", 0),
            "best_percent": row.get("best_percent"),
            "ever_wrong_question_count": row.get("ever_wrong_question_count"),
            "unresolved_wrong_question_count": row.get("unresolved_wrong_question_count"),
        },
        meta=meta(request),
    )


@router.get("/me/recommendations", response_model=Envelope[list[Recommendation]])
@access("progress.self")
async def recommendations(request: Request, limit: Annotated[int, Query(ge=1, le=10)] = 5) -> Any:
    return Envelope(data=await svc.recommendations(request, limit), meta=meta(request))


@router.get("/me/daily-topic", response_model=Envelope[DailyTopic])
@access("progress.self")
async def daily(request: Request) -> Any:
    return Envelope(data=await svc.daily(request), meta=meta(request))


@router.get("/me/achievements", response_model=Envelope[list[Achievement]])
@access("progress.self")
async def achievements(request: Request) -> Any:
    return Envelope(data=await svc.achievements(request), meta=meta(request))


@router.get("/me/home", response_model=Envelope[Home])
@access("progress.self")
async def home(request: Request) -> Any:
    db = current_db(request)
    user = current_identity(request).user
    active = await db.scalar(
        select(Attempt)
        .where(Attempt.user_id == user.id, Attempt.status == "in_progress")
        .with_for_update()
    )
    if active:
        await expire(db, active)
    recent, _ = await svc.history(request, limit=3)
    return Envelope(
        data={
            "statistics": await svc.summary(request),
            "active_attempt": await view(db, active)
            if active and active.status == "in_progress"
            else None,
            "recent_results": recent,
        },
        meta=meta(request),
    )


@router.get("/attempts/{attempt_id}/result-review", response_model=Envelope[ResultPage])
@access("progress.self")
async def result_review(
    attempt_id: UUID,
    request: Request,
    selection: Literal["all", "incorrect", "skipped"] = "incorrect",
    cursor: Cursor = None,
    limit: Limit = 30,
) -> Any:
    return Envelope(
        data=await svc.result_review(request, attempt_id, selection, cursor, limit),
        meta=meta(request),
    )
