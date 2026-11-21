"""Computed read models. Every SQL source is scoped to owner, epoch and completed status."""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.attempts.models import Attempt
from app.attempts.service import result_data
from app.content.cursors import decode_cursor, encode_cursor, filter_hash
from app.core.errors import ApplicationError
from app.identity.dependencies import current_db, current_identity

Period = Literal["all", "week", "month"]
BASE = """WITH completed AS (
 SELECT a.*, (a.finalized_at AT TIME ZONE a.timezone_at_start)::date AS activity_date
 FROM attempts a WHERE a.user_id=:uid AND a.progress_epoch=:epoch AND a.status='completed'
), chosen AS (
 SELECT * FROM completed WHERE (CAST(:start AS date) IS NULL OR activity_date>=:start)
 AND (CAST(:end AS date) IS NULL OR activity_date<=:end)
) """
ANSWERS = (
    BASE
    + """, answers AS (
 SELECT a.id AS aid, a.discipline_id, coalesce(i.topic_id,a.topic_id) AS topic_id,
 a.finalized_at, i.question_id, r.state, r.is_correct
 FROM chosen a JOIN attempt_items i ON i.attempt_id=a.id
 JOIN attempt_responses r ON r.item_id=i.id
) """
)


def fail(code: str, message: str, status: int = 422) -> ApplicationError:
    return ApplicationError(code, message, status)


async def clock(db: AsyncSession) -> datetime:
    now = await db.scalar(select(func.clock_timestamp()))
    assert now is not None
    return cast(datetime, now)


def params(request: Request, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    user = current_identity(request).user
    return {"uid": user.id, "epoch": user.progress_epoch, "start": start, "end": end}


def period_start(today: date, period: Period) -> date | None:
    if period == "week":
        return today - timedelta(days=today.weekday())
    if period == "month":
        return today.replace(day=1)
    return None


def day_in_zone(now: datetime, zone: str) -> date:
    return now.astimezone(ZoneInfo(zone)).date()


async def summary(request: Request, period: Period = "all") -> dict[str, Any]:
    db = current_db(request)
    user = current_identity(request).user
    now = await clock(db)
    today = day_in_zone(now, user.timezone)
    p = params(request, period_start(today, period), today if period != "all" else None)
    row = (
        (
            await db.execute(
                text(
                    BASE
                    + """SELECT count(*) AS completed_tests,
      coalesce(sum(answered),0) AS answered_count, coalesce(sum(correct),0) AS correct_count,
      coalesce(sum(wrong),0) AS wrong_count, coalesce(sum(skipped),0) AS skipped_count,
      round(avg(correct::numeric/total)*100)::int AS average_percent,
      sum(duration_seconds) AS practice_seconds FROM chosen"""
                ),
                p,
            )
        )
        .mappings()
        .one()
    )
    streak, _ = await streaks(request, today)
    return {
        **dict(row),
        "activity_streak_days": streak,
        "period": period,
        "timezone": user.timezone,
        "data_scope": "server_history",
        "calculated_at": now,
    }


async def streaks(request: Request, today: date) -> tuple[int, int]:
    p = params(request)
    p["today"] = today
    row = (
        (
            await current_db(request).execute(
                text(
                    BASE
                    + """, days AS (
      SELECT DISTINCT activity_date AS d FROM chosen
    ), islands AS (SELECT d, d-row_number() OVER(ORDER BY d)::int AS g FROM days),
    runs AS (SELECT min(d) AS first, max(d) AS last, count(*)::int AS n FROM islands GROUP BY g)
    SELECT coalesce(max(n) FILTER(WHERE last BETWEEN
      CAST(:today AS date)-1 AND :today),0) AS current,
    coalesce(max(n),0) AS longest FROM runs"""
                ),
                p,
            )
        )
        .mappings()
        .one()
    )
    return int(row["current"]), int(row["longest"])


def cursor_key(request: Request) -> str:
    key = request.app.state.settings.content_cursor_signing_key
    if key is None:
        raise fail("PROGRESS_CURSOR_NOT_CONFIGURED", "Пагинация ещё не настроена.", 503)
    return str(key.get_secret_value())


def cursor_scope(request: Request, route: str, filters: dict[str, Any]) -> str:
    user = current_identity(request).user
    return filter_hash(
        {
            "route": "progress:" + route,
            "owner": str(user.id),
            "epoch": user.progress_epoch,
            **filters,
        }
    )


async def history(
    request: Request,
    *,
    mode: str | None = None,
    discipline_id: UUID | None = None,
    topic_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if start and end and start > end:
        raise fail("INVALID_PERIOD", "Начало периода должно предшествовать концу.")
    db = current_db(request)
    user = current_identity(request).user
    s = select(Attempt).where(
        Attempt.user_id == user.id,
        Attempt.progress_epoch == user.progress_epoch,
        Attempt.status == "completed",
    )
    if mode:
        s = s.where(Attempt.mode == mode)
    if discipline_id:
        s = s.where(Attempt.discipline_id == discipline_id)
    if topic_id:
        from app.attempts.models import AttemptItem

        s = s.where(
            select(AttemptItem.id)
            .where(
                AttemptItem.attempt_id == Attempt.id,
                func.coalesce(AttemptItem.topic_id, Attempt.topic_id) == topic_id,
            )
            .exists()
        )
    local_day = func.date(func.timezone(Attempt.timezone_at_start, Attempt.finalized_at))
    if start:
        s = s.where(local_day >= start)
    if end:
        s = s.where(local_day <= end)
    scope = cursor_scope(
        request,
        "history",
        {
            "mode": mode,
            "discipline": str(discipline_id) if discipline_id else None,
            "topic": str(topic_id) if topic_id else None,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
    )
    if cursor:
        position, entity = decode_cursor(cursor, cursor_key(request), version=1, scope=scope)
        stamp = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=position)
        from sqlalchemy import tuple_

        s = s.where(
            tuple_(Attempt.finalized_at, Attempt.id) < tuple_(literal(stamp), literal(UUID(entity)))
        )
    rows = (
        await db.scalars(
            s.order_by(Attempt.finalized_at.desc(), Attempt.id.desc()).limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        a = rows[-1]
        assert a.finalized_at is not None
        delta = a.finalized_at - datetime(1970, 1, 1, tzinfo=UTC)
        us = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        next_cursor = encode_cursor(
            cursor_key(request), version=1, scope=scope, position=us, entity_id=str(a.id)
        )
    return [history_item(a) for a in rows], {"next_cursor": next_cursor, "has_more": more}


def history_item(a: Attempt) -> dict[str, Any]:
    assert a.finalized_at is not None
    return {
        "id": a.id,
        "mode": a.mode,
        "discipline_id": a.discipline_id,
        "topic_id": a.topic_id,
        "test_definition_id": a.test_definition_id,
        "result": result_data(a),
        "activity_date": day_in_zone(a.finalized_at, a.timezone_at_start),
        "activity_timezone": a.timezone_at_start,
    }


async def activity(request: Request, start: date, end: date) -> dict[str, Any]:
    if end < start or (end - start).days > 365:
        raise fail("INVALID_PERIOD", "Выберите период от 1 до 366 календарных дней.")
    rows = (
        (
            await current_db(request).execute(
                text(
                    BASE
                    + """SELECT activity_date,
      count(*) AS completed_tests, sum(answered) AS answered_count, sum(correct) AS correct_count,
      sum(duration_seconds) AS practice_seconds,
      round(avg(correct::numeric/total)*100)::int AS average_percent
      FROM chosen GROUP BY activity_date ORDER BY activity_date"""
                ),
                params(request, start, end),
            )
        )
        .mappings()
        .all()
    )
    by_day = {r["activity_date"]: dict(r) for r in rows}
    days = []
    for i in range((end - start).days + 1):
        d = start + timedelta(days=i)
        row = by_day.get(
            d,
            {
                "completed_tests": 0,
                "answered_count": 0,
                "correct_count": 0,
                "practice_seconds": 0,
                "average_percent": None,
            },
        )
        days.append({"date": d, **{k: v for k, v in row.items() if k != "activity_date"}})
    return {
        "timezone": current_identity(request).user.timezone,
        "date_policy": "frozen_attempt_timezone",
        "start": start,
        "end": end,
        "days": days,
    }


GROUPS = """, per_attempt AS (
 SELECT {dimension} AS gid, aid, count(*) AS total, count(*) FILTER(WHERE is_correct) AS correct
 FROM answers WHERE {dimension} IS NOT NULL GROUP BY {dimension}, aid
), grades AS (SELECT gid, count(*) AS completed_tests,
 round(avg(correct::numeric/total)*100)::int AS average_percent,
 round(max(correct::numeric/total)*100)::int AS best_percent FROM per_attempt GROUP BY gid),
last_choices AS (SELECT {dimension} AS gid, question_id, is_correct,
 row_number() OVER(PARTITION BY {dimension},question_id ORDER BY finalized_at DESC,aid DESC) AS rn
 FROM answers WHERE state='committed' AND {dimension} IS NOT NULL),
unresolved AS (SELECT gid,count(*) FILTER(WHERE NOT is_correct)::int AS n
 FROM last_choices WHERE rn=1 GROUP BY gid),
counts AS (SELECT {dimension} AS gid, count(*) FILTER(WHERE state='committed') AS answered_count,
 count(*) FILTER(WHERE is_correct) AS correct_count,
 count(*) FILTER(WHERE state='committed' AND NOT is_correct) AS wrong_count,
 count(*) FILTER(WHERE state='skipped') AS skipped_count,
 count(DISTINCT question_id) AS observed_questions,
 count(DISTINCT question_id) FILTER(WHERE state='committed' AND NOT is_correct)
 AS ever_wrong_question_count
 FROM answers WHERE {dimension} IS NOT NULL GROUP BY {dimension})
 SELECT c.gid AS id, label.title, g.completed_tests, c.answered_count,c.correct_count,c.wrong_count,
 c.skipped_count,c.observed_questions,g.average_percent,g.best_percent,c.ever_wrong_question_count,
 coalesce(u.n,0) AS unresolved_wrong_question_count FROM counts c JOIN grades g ON g.gid=c.gid
 JOIN {table} label ON label.id=c.gid LEFT JOIN unresolved u ON u.gid=c.gid
"""


async def groups(
    request: Request,
    dimension: Literal["discipline_id", "topic_id"],
    *,
    after: UUID | None = None,
    limit: int = 30,
    only: UUID | None = None,
    discipline_id: UUID | None = None,
    weak: bool = False,
) -> list[dict[str, Any]]:
    # SQL identifiers come exclusively from this fixed internal allowlist.
    table = "disciplines" if dimension == "discipline_id" else "topics"
    query = ANSWERS + GROUPS.format(dimension=dimension, table=table)
    p = params(request)
    where = []
    if after:
        where.append("c.gid>:after")
        p["after"] = after
    if only:
        where.append("c.gid=:only")
        p["only"] = only
    if discipline_id and dimension == "topic_id":
        where.append("label.discipline_id=:discipline")
        p["discipline"] = discipline_id
    if weak:
        where.extend(["c.answered_count>0", "g.average_percent<70"])
    if where:
        query += " WHERE " + " AND ".join(where)
    query += (
        " ORDER BY "
        + ("g.average_percent ASC, coalesce(u.n,0) DESC, c.gid" if weak else "c.gid")
        + " LIMIT :limit"
    )
    p["limit"] = limit
    return [dict(r) for r in (await current_db(request).execute(text(query), p)).mappings()]


async def unattributed(request: Request) -> int:
    n = await current_db(request).scalar(
        text(ANSWERS + " SELECT count(*) FROM answers WHERE topic_id IS NULL"), params(request)
    )
    return int(n or 0)


async def recommendations(request: Request, limit: int = 5) -> list[dict[str, Any]]:
    from app.content.models import Topic
    from app.content.queries import count_questions_for, visible_topics

    candidates = await groups(request, "topic_id", weak=True, limit=100)
    if not candidates:
        return []
    rows = (
        (
            await current_db(request).execute(
                visible_topics()
                .add_columns(count_questions_for(Topic.id).label("question_count"))
                .where(Topic.id.in_([r["id"] for r in candidates]))
            )
        )
        .mappings()
        .all()
    )
    available = {r["id"]: r for r in rows if r["question_count"] > 0}
    result = []
    for candidate in candidates:
        row = available.get(candidate["id"])
        if row is not None:
            result.append(
                {
                    "topic_id": row["id"],
                    "discipline_id": row["discipline_id"],
                    "title": row["title"],
                    "question_count": row["question_count"],
                    "reason": "weak_topic",
                    "observed_average_percent": candidate["average_percent"],
                    "observed_attempts": candidate["completed_tests"],
                }
            )
        if len(result) >= limit:
            break
    return result


async def daily(request: Request) -> dict[str, Any]:
    from app.content.models import CatalogState, Topic
    from app.content.queries import count_questions_for, visible_topics
    from app.progress.models import DailyRecommendation

    db = current_db(request)
    user = current_identity(request).user
    today = day_in_zone(await clock(db), user.timezone)
    saved = await db.get(DailyRecommendation, (user.id, today))
    if saved is None:
        state = await db.scalar(
            select(CatalogState).where(CatalogState.id == 1).with_for_update(read=True)
        )
        if state is None:
            raise fail("SERVICE_NOT_READY", "Каталог не готов.", 503)
        recs = await recommendations(request, 1)
        tid = recs[0]["topic_id"] if recs else None
        if tid is None:
            eligible = visible_topics().where(count_questions_for(Topic.id) > 0).subquery()
            count = int(await db.scalar(select(func.count()).select_from(eligible)) or 0)
            if count:
                tid = await db.scalar(
                    select(eligible.c.id)
                    .order_by(eligible.c.id)
                    .offset(today.toordinal() % count)
                    .limit(1)
                )
        saved = DailyRecommendation(
            user_id=user.id,
            local_date=today,
            topic_id=tid,
            timezone=user.timezone,
            catalog_version=state.version,
        )
        db.add(saved)
        await db.flush()
    row = None
    if saved.topic_id:
        row = (
            (
                await db.execute(
                    visible_topics()
                    .add_columns(count_questions_for(Topic.id).label("question_count"))
                    .where(Topic.id == saved.topic_id)
                )
            )
            .mappings()
            .one_or_none()
        )
    display = dict(row) if row is not None else {}
    available = bool(display.get("question_count", 0) > 0)
    return {
        "local_date": saved.local_date,
        "timezone": saved.timezone,
        "topic_id": saved.topic_id,
        "title": display["title"] if available else None,
        "discipline_id": display["discipline_id"] if available else None,
        "question_count": display["question_count"] if available else None,
        "availability": "available" if available else ("withdrawn" if saved.topic_id else "empty"),
        "catalog_version": saved.catalog_version,
        "selector_version": saved.selector_version,
    }


async def achievements(request: Request) -> list[dict[str, Any]]:
    db = current_db(request)
    s = await summary(request)
    today = day_in_zone(await clock(db), current_identity(request).user.timezone)
    _, longest = await streaks(request, today)
    perfect = bool(
        await db.scalar(
            text(BASE + " SELECT EXISTS(SELECT 1 FROM chosen WHERE correct=total)"), params(request)
        )
    )
    configured = [
        ("first", "Первый шаг", "Первый завершённый тест", s["completed_tests"], 1),
        (
            "three",
            "Три дня",
            "Три последовательных календарных дня с завершёнными тестами",
            longest,
            3,
        ),
        (
            "hundred",
            "Сотня",
            "100 правильных ответов в завершённых тестах",
            s["correct_count"],
            100,
        ),
        (
            "perfect",
            "Без ошибок",
            "Завершённый тест со всеми правильными ответами",
            int(perfect),
            1,
        ),
    ]
    result = [
        {
            "code": c,
            "title": title,
            "condition": condition,
            "state": "unlocked" if value >= target else "locked",
            "progress": min(value, target),
            "target": target,
            "granted_at": None,
        }
        for c, title, condition, value, target in configured
    ]
    for code, title, condition in [
        ("anatomy", "Анатом", "Учебный блок пока не настроен"),
        ("clinical", "Клиницист", "Клинический блок пока не настроен"),
        ("pharmacy", "Провизор", "Блок фармакологии пока не настроен"),
        ("memory", "Память", "Учёт исправленных ошибок пока не настроен"),
        ("finish", "Финиш", "Учебный маршрут пока не настроен"),
    ]:
        result.append(
            {
                "code": code,
                "title": title,
                "condition": condition,
                "state": "not_configured",
                "progress": None,
                "target": None,
                "granted_at": None,
            }
        )
    order = [
        "first",
        "three",
        "anatomy",
        "clinical",
        "pharmacy",
        "hundred",
        "perfect",
        "memory",
        "finish",
    ]
    return sorted(result, key=lambda r: order.index(str(r["code"])))


async def result_review(
    request: Request, attempt_id: UUID, selection: str, cursor: str | None, limit: int
) -> dict[str, Any]:
    from app.attempts.models import AttemptItem, AttemptOption, AttemptResponse
    from app.attempts.service import error, owned
    from app.content.api import guard_exam_reference
    from app.content.models import QuestionOption, QuestionRevision

    a = await owned(request, attempt_id, lock=True)
    if a.status != "completed":
        raise error("RESULT_NOT_AVAILABLE")
    await guard_exam_reference(request)
    db = current_db(request)
    scope = cursor_scope(
        request, "result-review", {"attempt_id": str(a.id), "selection": selection}
    )
    s = (
        select(AttemptItem, AttemptResponse)
        .join(AttemptResponse, AttemptResponse.item_id == AttemptItem.id)
        .where(AttemptItem.attempt_id == a.id)
    )
    if selection == "incorrect":
        s = s.where((AttemptResponse.is_correct.is_(False)) | (AttemptResponse.state == "skipped"))
    elif selection == "skipped":
        s = s.where(AttemptResponse.state == "skipped")
    if cursor:
        position, entity = decode_cursor(cursor, cursor_key(request), version=1, scope=scope)
        if entity != str(a.id):
            raise fail("INVALID_CURSOR", "Некорректный cursor.", 400)
        s = s.where(AttemptItem.position > position)
    pairs = (await db.execute(s.order_by(AttemptItem.position).limit(limit + 1))).all()
    more = len(pairs) > limit
    pairs = pairs[:limit]
    ids = [item.id for item, _ in pairs]
    revision_ids = [item.revision_id for item, _ in pairs]
    revisions = {
        r.id: r
        for r in (
            await db.scalars(select(QuestionRevision).where(QuestionRevision.id.in_(revision_ids)))
        ).all()
    }
    options: dict[UUID, list[Any]] = {}
    for option in (
        await db.execute(
            select(AttemptOption.item_id, AttemptOption.position, QuestionOption)
            .join(QuestionOption, QuestionOption.id == AttemptOption.option_id)
            .where(AttemptOption.item_id.in_(ids))
            .order_by(AttemptOption.item_id, AttemptOption.position)
        )
    ).all():
        options.setdefault(option.item_id, []).append(option)
    result = []
    for item, response in pairs:
        rev = revisions[item.revision_id]
        opts = options.get(item.id, [])
        result.append(
            {
                "id": str(item.id),
                "question_id": str(item.question_id),
                "revision_id": str(item.revision_id),
                "position": item.position,
                "text": rev.text,
                "options": [
                    {"id": str(o.id), "position": pos, "code": o.code, "text": o.text}
                    for _, pos, o in opts
                ],
                "selected_option_ids": [str(response.selected_option_id)]
                if response.selected_option_id
                else [],
                "is_correct": response.is_correct,
                "correct_option_ids": [str(o.id) for _, _, o in opts if o.is_correct],
            }
        )
    token = (
        encode_cursor(
            cursor_key(request),
            version=1,
            scope=scope,
            position=pairs[-1][0].position,
            entity_id=str(a.id),
        )
        if more
        else None
    )
    return {"items": result, "next_cursor": token, "has_more": more}
