"""All commands run in the existing identity transaction (user -> attempt lock)."""

from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import QuestionBody
from app.attempts.models import Attempt, AttemptCommand, AttemptItem, AttemptOption, AttemptResponse
from app.attempts.schemas import AttemptView, Start
from app.content.models import (
    CatalogState,
    Discipline,
    QuestionOption,
    QuestionRevision,
    TestDefinition,
    Topic,
)
from app.content.queries import visible_questions, visible_topics
from app.core.errors import ApplicationError
from app.core.idempotency import StoredResponse, request_fingerprint, run_idempotent
from app.identity.dependencies import current_db, current_identity
from app.identity.service import audit


def error(
    code: str, message: str = "Действие недоступно. Обновите состояние попытки.", status: int = 409
) -> ApplicationError:
    return ApplicationError(code, message, status)


def etag(attempt: Attempt) -> str:
    return f'"attempt-{attempt.id}-{attempt.version}"'


async def owned(request: Request, attempt_id: UUID, *, lock: bool = False) -> Attempt:
    statement = select(Attempt).where(
        Attempt.id == attempt_id, Attempt.user_id == current_identity(request).user.id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    attempt = await current_db(request).scalar(statement)
    if attempt is None:
        raise error("NOT_FOUND", "Попытка не найдена.", 404)
    return attempt


def result_data(a: Attempt) -> dict[str, Any]:
    return {
        "attempt_id": str(a.id),
        "title": a.frozen_title,
        "total": a.total,
        "correct": a.correct,
        "wrong": a.wrong,
        "skipped": a.skipped,
        "answered": a.answered,
        "percent": a.percent,
        "duration_seconds": a.duration_seconds,
        "started_at": a.started_at.isoformat(),
        "finalized_at": a.finalized_at.isoformat() if a.finalized_at else None,
        "finish_reason": a.finish_reason,
    }


async def view(
    db: AsyncSession, a: Attempt, projection: dict[str, Any] | None = None
) -> dict[str, Any]:
    status = str(projection["status"]) if projection else a.status
    version = int(projection["version"]) if projection else a.version
    position = int(projection["current_position"]) if projection else a.current_position
    data: dict[str, Any] = {
        "id": str(a.id),
        "mode": "learning",
        "status": status,
        "version": version,
        "title": a.frozen_title,
        "scope": a.scope,
        "discipline_id": str(a.discipline_id),
        "topic_id": str(a.topic_id) if a.topic_id else None,
        "test_definition_id": str(a.test_definition_id) if a.test_definition_id else None,
        "total": a.total,
        "current_position": position,
        "started_at": a.started_at.isoformat(),
        "current_item": None,
    }
    if status == "completed":
        data["result"] = result_data(a)
    if status != "in_progress":
        return data
    item = await db.scalar(
        select(AttemptItem).where(AttemptItem.attempt_id == a.id, AttemptItem.position == position)
    )
    assert item is not None
    rev = await db.get(QuestionRevision, item.revision_id)
    assert rev is not None
    options = (
        await db.execute(
            select(
                AttemptOption.option_id,
                AttemptOption.position,
                QuestionOption.code,
                QuestionOption.text,
            )
            .join(QuestionOption, QuestionOption.id == AttemptOption.option_id)
            .where(AttemptOption.item_id == item.id)
            .order_by(AttemptOption.position)
        )
    ).all()
    response = (
        await db.get(AttemptResponse, item.id)
        if projection is None or projection["checked"]
        else None
    )
    current: dict[str, Any] = {
        "id": str(item.id),
        "question_id": str(item.question_id),
        "revision_id": str(item.revision_id),
        "position": item.position,
        "text": rev.text,
        "options": [
            {"id": str(o.option_id), "position": o.position, "code": o.code, "text": o.text}
            for o in options
        ],
        "state": "checked" if response is not None else "awaiting_answer",
        "selected_option_ids": [],
    }
    if response is not None:
        assert response.state == "committed"
        keys = list(
            (
                await db.scalars(
                    select(QuestionOption.id)
                    .join(AttemptOption, AttemptOption.option_id == QuestionOption.id)
                    .where(AttemptOption.item_id == item.id, QuestionOption.is_correct.is_(True))
                    .order_by(AttemptOption.position)
                )
            ).all()
        )
        feedback: dict[str, Any] = {
            "is_correct": response.is_correct,
            "correct_option_ids": [str(k) for k in keys],
        }
        if rev.explanation:
            feedback["explanation"] = rev.explanation
        current["selected_option_ids"] = [str(response.selected_option_id)]
        current["feedback"] = feedback
    data["current_item"] = current
    return data


async def create(request: Request, body: Start) -> Attempt:
    db = current_db(request)
    identity = current_identity(request)
    active = await db.scalar(
        select(Attempt.id).where(
            Attempt.user_id == identity.user.id, Attempt.status == "in_progress"
        )
    )
    if active:
        raise ApplicationError(
            "ACTIVE_ATTEMPT_EXISTS",
            "Продолжите активную попытку или подтвердите выход.",
            409,
            {"attempt_id": str(active)},
        )
    state = await db.scalar(
        select(CatalogState).where(CatalogState.id == 1).with_for_update(read=True)
    )
    if state is None:
        raise error("SERVICE_NOT_READY", status=503)
    scope = "discipline"
    topic_id = None
    definition_id = None
    if body.test_definition_id:
        definition = await db.get(TestDefinition, body.test_definition_id)
        if definition is None or definition.status != "published":
            raise error("NOT_FOUND", "Тест недоступен.", 404)
        if (
            definition.selection_policy != "ordered_all"
            or definition.policy_version != 1
            or definition.question_limit is not None
        ):
            raise error(
                "UNSUPPORTED_SELECTION",
                "Поддерживается только полный упорядоченный набор policy v1.",
                422,
            )
        topic_id = definition.topic_id
        definition_id = definition.id
        scope = "test"
        title = definition.title
    elif body.topic_id:
        topic_id = body.topic_id
        scope = "topic"
    if topic_id:
        topic = (
            (await db.execute(visible_topics().where(Topic.id == topic_id)))
            .mappings()
            .one_or_none()
        )
        if topic is None:
            raise error("NOT_FOUND", "Тема недоступна.", 404)
        discipline_id = topic["discipline_id"]
        if scope == "topic":
            title = topic["title"]
    else:
        discipline = await db.get(Discipline, body.discipline_id)
        if discipline is None or discipline.status != "published":
            raise error("NOT_FOUND", "Дисциплина недоступна.", 404)
        discipline_id = discipline.id
        title = discipline.title
    q = visible_questions().subquery()
    t = visible_topics().subquery()
    ranked = (
        select(
            q.c.id,
            q.c.revision_id,
            q.c.position,
            q.c.topic_id,
            t.c.position.label("topic_position"),
            func.row_number()
            .over(partition_by=q.c.id, order_by=(t.c.position, t.c.id, q.c.position, q.c.id))
            .label("rank"),
        )
        .join(t, t.c.id == q.c.topic_id)
        .where(q.c.discipline_id == discipline_id)
    )
    if topic_id:
        ranked = ranked.where(q.c.topic_id == topic_id)
    ranks = ranked.subquery()
    selected = (
        await db.execute(
            select(ranks.c.id, ranks.c.revision_id)
            .where(ranks.c.rank == 1)
            .order_by(ranks.c.topic_position, ranks.c.topic_id, ranks.c.position, ranks.c.id)
            .limit(5001)
        )
    ).all()
    if not selected:
        raise error("EMPTY_QUESTION_SET", "В выбранном наборе нет доступных вопросов.")
    if len(selected) > 5000:
        raise error("ATTEMPT_LIMIT", "Выберите тему или тест до 5000 вопросов.", 422)
    ids = [row.revision_id for row in selected]
    revisions = {
        r.id: r
        for r in (
            await db.scalars(select(QuestionRevision).where(QuestionRevision.id.in_(ids)))
        ).all()
    }
    options: dict[UUID, list[QuestionOption]] = {}
    for option in (
        await db.scalars(
            select(QuestionOption)
            .where(QuestionOption.revision_id.in_(ids))
            .order_by(QuestionOption.revision_id, QuestionOption.position)
        )
    ).all():
        options.setdefault(option.revision_id, []).append(option)
    for rid in ids:
        rev = revisions[rid]
        opts = options.get(rid, [])
        try:
            validated = QuestionBody(
                kind=rev.kind,
                text=rev.text,
                options=[
                    {"code": o.code, "text": o.text, "is_correct": o.is_correct} for o in opts
                ],
            )
            if validated.kind != "single_choice":
                raise ValueError("Unsupported kind")
        except (ValidationError, ValueError):
            raise error(
                "INVALID_QUESTION_SET", "Набор содержит неподдерживаемый вопрос.", 422
            ) from None
    attempt = Attempt(
        id=uuid4(),
        user_id=identity.user.id,
        scope=scope,
        discipline_id=discipline_id,
        topic_id=topic_id,
        test_definition_id=definition_id,
        progress_epoch=identity.user.progress_epoch,
        timezone_at_start=identity.user.timezone,
        frozen_title=title,
        catalog_version=state.version,
        total=len(selected),
    )
    db.add(attempt)
    await db.flush()
    items = [
        AttemptItem(
            id=uuid4(),
            attempt_id=attempt.id,
            question_id=row.id,
            revision_id=row.revision_id,
            position=i,
        )
        for i, row in enumerate(selected)
    ]
    db.add_all(items)
    await db.flush()
    db.add_all(
        [
            AttemptOption(item_id=item.id, revision_id=item.revision_id, option_id=o.id, position=i)
            for item in items
            for i, o in enumerate(options[item.revision_id])
        ]
    )
    await db.flush()
    attempt.snapshot_ready = True
    await db.flush()
    audit(
        db,
        actor=identity.user.id,
        action="attempt.started",
        entity_type="attempt",
        entity_id=attempt.id,
        request_id=UUID(request.state.request_id),
    )
    return attempt


async def finalize(db: AsyncSession, a: Attempt, reason: str) -> None:
    answered = set(
        (
            await db.scalars(
                select(AttemptResponse.item_id).where(AttemptResponse.attempt_id == a.id)
            )
        ).all()
    )
    remaining = (
        await db.scalars(
            select(AttemptItem).where(AttemptItem.attempt_id == a.id).order_by(AttemptItem.position)
        )
    ).all()
    db.add_all(
        [
            AttemptResponse(
                item_id=i.id, attempt_id=a.id, revision_id=i.revision_id, state="skipped"
            )
            for i in remaining
            if i.id not in answered
        ]
    )
    await db.flush()
    records = (
        await db.execute(
            select(AttemptResponse.state, AttemptResponse.is_correct).where(
                AttemptResponse.attempt_id == a.id
            )
        )
    ).all()
    a.correct = sum(s == "committed" and correct is True for s, correct in records)
    a.wrong = sum(s == "committed" and correct is False for s, correct in records)
    a.skipped = sum(s == "skipped" for s, _ in records)
    a.answered = a.correct + a.wrong
    a.percent = (2 * a.correct * 100 + a.total) // (2 * a.total)
    a.finalized_at = await db.scalar(select(func.clock_timestamp()))
    assert a.finalized_at
    a.duration_seconds = max(0, int((a.finalized_at - a.started_at).total_seconds()))
    a.status = "completed"
    a.finish_reason = reason


async def mutate(
    request: Request, a: Attempt, operation: str, body: Any, item_id: UUID | None
) -> None:
    db = current_db(request)
    if a.status != "in_progress":
        raise error("ATTEMPT_CLOSED")
    current = await db.scalar(
        select(AttemptItem).where(
            AttemptItem.attempt_id == a.id, AttemptItem.position == a.current_position
        )
    )
    assert current
    if item_id is not None and item_id != current.id:
        raise error("CURRENT_ITEM_REQUIRED")
    response = await db.get(AttemptResponse, current.id)
    if operation == "submit":
        if response is not None:
            raise error("ANSWER_LOCKED", "Ответ уже зафиксирован.")
        oid = body.selected_option_ids[0]
        option = await db.scalar(
            select(QuestionOption)
            .join(AttemptOption, AttemptOption.option_id == QuestionOption.id)
            .where(AttemptOption.item_id == current.id, AttemptOption.option_id == oid)
        )
        if option is None:
            raise error("INVALID_OPTION", "Вариант не принадлежит текущему вопросу.", 422)
        db.add(
            AttemptResponse(
                item_id=current.id,
                attempt_id=a.id,
                revision_id=current.revision_id,
                state="committed",
                selected_option_id=oid,
                is_correct=option.is_correct,
            )
        )
        await db.flush()
    elif operation in ("advance", "skip"):
        if operation == "advance" and (response is None or response.state != "committed"):
            raise error("ANSWER_REQUIRED")
        if operation == "skip":
            if response is not None:
                raise error("ANSWER_LOCKED")
            db.add(
                AttemptResponse(
                    item_id=current.id,
                    attempt_id=a.id,
                    revision_id=current.revision_id,
                    state="skipped",
                )
            )
            await db.flush()
        if a.current_position == a.total - 1:
            await finalize(db, a, "last_question")
        else:
            a.current_position += 1
    elif operation == "finish":
        await finalize(db, a, "user_finish")
    elif operation == "abandon":
        a.status = "abandoned"
        a.finish_reason = "user_exit"
        a.finalized_at = await db.scalar(select(func.clock_timestamp()))
    a.version += 1
    await db.flush()
    audit(
        db,
        actor=a.user_id,
        action="attempt." + operation,
        entity_type="attempt",
        entity_id=a.id,
        request_id=UUID(request.state.request_id),
    )


async def command(
    request: Request,
    key: UUID,
    operation: str,
    body: Any,
    attempt_id: UUID | None = None,
    item_id: UUID | None = None,
) -> dict[str, Any]:
    db = current_db(request)
    actor = current_identity(request).user.id
    if attempt_id is not None:
        await owned(request, attempt_id)
    payload = {
        "attempt_id": str(attempt_id) if attempt_id else None,
        "item_id": str(item_id) if item_id else None,
        "if_match": request.headers.get("if-match") if attempt_id else None,
        "body": body.model_dump(mode="json"),
    }

    async def apply(session: AsyncSession) -> StoredResponse:
        h = request_fingerprint(payload)
        receipt = await session.scalar(
            select(AttemptCommand).where(
                AttemptCommand.actor_id == actor,
                AttemptCommand.operation == operation,
                AttemptCommand.key == key,
            )
        )
        if receipt:
            if receipt.request_hash != h:
                raise error("IDEMPOTENCY_KEY_REUSED")
            original = await owned(request, receipt.attempt_id)
            replay = AttemptView.model_validate(
                await view(session, original, receipt.result)
            ).model_dump(mode="json")
            return StoredResponse(200, replay, receipt.attempt_id)
        if attempt_id is None:
            a = await create(request, body)
        else:
            a = await owned(request, attempt_id, lock=True)
            if request.headers.get("if-match") is None:
                raise error("PRECONDITION_REQUIRED", "Требуется If-Match версии попытки.", 412)
            if request.headers["if-match"] != etag(a):
                raise ApplicationError(
                    "ATTEMPT_VERSION_CONFLICT",
                    "Попытка изменилась. Перечитайте состояние.",
                    409,
                    {"version": a.version},
                )
            await mutate(request, a, operation, body, item_id)
        data = AttemptView.model_validate(await view(db, a)).model_dump(mode="json")
        session.add(
            AttemptCommand(
                actor_id=actor,
                attempt_id=a.id,
                operation=operation,
                key=key,
                request_hash=h,
                result={
                    "status": data["status"],
                    "version": data["version"],
                    "current_position": data["current_position"],
                    "checked": data["current_item"] is not None
                    and data["current_item"]["state"] == "checked",
                },
            )
        )
        await session.flush()
        return StoredResponse(200, data, a.id)

    result = await run_idempotent(
        db,
        actor_id=actor,
        operation="learning." + operation,
        key=key,
        payload=payload,
        action=apply,
    )
    return cast(dict[str, Any], result.response.body)
