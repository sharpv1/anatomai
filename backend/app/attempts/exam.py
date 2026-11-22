"""Exam drafts never expose feedback; only finalization creates scored responses."""

import math
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.attempts.models import Attempt, AttemptItem, AttemptOption, AttemptResponse, ExamAnswer
from app.content.models import QuestionOption, QuestionRevision
from app.identity.dependencies import current_db
from app.identity.service import audit


async def item_data(db: AsyncSession, item: AttemptItem) -> dict[str, Any]:
    revision = await db.get(QuestionRevision, item.revision_id)
    assert revision is not None
    rows = (
        await db.execute(
            select(AttemptOption.position, QuestionOption)
            .join(QuestionOption, QuestionOption.id == AttemptOption.option_id)
            .where(AttemptOption.item_id == item.id)
            .order_by(AttemptOption.position)
        )
    ).all()
    return {
        "id": str(item.id),
        "question_id": str(item.question_id),
        "revision_id": str(item.revision_id),
        "position": item.position,
        "text": revision.text,
        "options": [
            {"id": str(o.id), "position": pos, "code": o.code, "text": o.text} for pos, o in rows
        ],
    }


async def exam_view(
    db: AsyncSession, a: Attempt, projection: dict[str, Any] | None = None
) -> dict[str, Any]:
    from app.attempts.service import result_data

    status = str(projection["status"]) if projection else a.status
    position = int(projection["current_position"]) if projection else a.current_position
    version = int(projection["version"]) if projection else a.version
    now = await db.scalar(select(func.clock_timestamp()))
    assert now is not None and a.deadline_at is not None
    data = {
        "id": str(a.id),
        "mode": "exam",
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
        "deadline_at": a.deadline_at.isoformat(),
        "remaining_seconds": int(projection["remaining_seconds"])
        if projection
        else (
            max(0, math.ceil((a.deadline_at - now).total_seconds()))
            if status == "in_progress"
            else 0
        ),
        "current_item": None,
    }
    if status == "completed":
        data["result"] = result_data(a)
    if status == "in_progress":
        item = await db.scalar(
            select(AttemptItem).where(
                AttemptItem.attempt_id == a.id, AttemptItem.position == position
            )
        )
        assert item is not None
        current = await item_data(db, item)
        answer = await db.get(ExamAnswer, item.id)
        current.update(
            state="draft",
            selected_option_ids=projection["selected_option_ids"]
            if projection
            else ([str(answer.selected_option_id)] if answer and answer.selected_option_id else []),
        )
        data["current_item"] = current
    return data


async def finalize_exam(db: AsyncSession, a: Attempt, reason: str) -> None:
    from app.attempts.service import finalize

    answers = (
        await db.execute(
            select(ExamAnswer, QuestionOption.is_correct)
            .join(QuestionOption, QuestionOption.id == ExamAnswer.selected_option_id)
            .where(ExamAnswer.attempt_id == a.id)
        )
    ).all()
    db.add_all(
        [
            AttemptResponse(
                item_id=e.item_id,
                attempt_id=a.id,
                revision_id=e.revision_id,
                selected_option_id=e.selected_option_id,
                state="committed",
                is_correct=correct,
            )
            for e, correct in answers
        ]
    )
    await db.flush()
    now = await db.scalar(select(func.clock_timestamp()))
    assert now is not None and a.deadline_at is not None
    if now >= a.deadline_at:
        reason = "timeout"
    await finalize(db, a, reason)
    a.version += 1
    await db.flush()
    audit(
        db,
        actor=a.user_id,
        action="exam.finalized." + str(a.finish_reason),
        entity_type="attempt",
        entity_id=a.id,
        request_id=uuid4(),
    )


async def expire(db: AsyncSession, a: Attempt) -> bool:
    """Caller holds user lock then attempt lock; DB time is the authority."""
    if a.mode != "exam" or a.status != "in_progress":
        return False
    now = await db.scalar(select(func.clock_timestamp()))
    assert now is not None and a.deadline_at is not None
    if now < a.deadline_at:
        return False
    await finalize_exam(db, a, "timeout")
    return True


async def mutate_exam(
    request: Request, a: Attempt, operation: str, body: Any, item_id: UUID | None
) -> None:
    from app.attempts.service import error

    db = current_db(request)
    # Successful terminal response commits timeout instead of rolling it back via HTTP error.
    if await expire(db, a):
        return
    if a.status != "in_progress":
        raise error("ATTEMPT_CLOSED")
    if operation == "submit":
        raise error("EXAM_SUBMIT_FORBIDDEN", "В экзамене используется сохранение черновика.", 422)
    if operation == "finish":
        await finalize_exam(db, a, "user_finish")
        return
    if operation == "draft":
        item = await db.scalar(
            select(AttemptItem).where(AttemptItem.id == item_id, AttemptItem.attempt_id == a.id)
        )
        if item is None:
            raise error("NOT_FOUND", status=404)
        oid = body.selected_option_ids[0] if body.selected_option_ids else None
        if oid is not None and await db.get(AttemptOption, (item.id, oid)) is None:
            raise error("INVALID_OPTION", "Вариант не принадлежит вопросу.", 422)
        try:
            async with db.begin_nested():
                answer = await db.get(ExamAnswer, item.id)
                if answer is None:
                    db.add(
                        ExamAnswer(
                            item_id=item.id,
                            attempt_id=a.id,
                            revision_id=item.revision_id,
                            selected_option_id=oid,
                        )
                    )
                else:
                    answer.selected_option_id = oid
                    # Even same-choice saves are versioned commands.
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(answer, "selected_option_id")
                await db.flush()
        except DBAPIError:
            # Deadline can cross between application check and the INSERT/UPDATE trigger.
            # Roll back only this draft; preserve earlier answers, commit timeout.
            if await expire(db, a):
                return
            raise
    elif operation == "navigate":
        if body.position >= a.total:
            raise error("INVALID_POSITION", status=422)
        a.current_position = body.position
    elif operation in ("advance", "skip"):
        item = await db.scalar(
            select(AttemptItem.id).where(
                AttemptItem.attempt_id == a.id, AttemptItem.position == a.current_position
            )
        )
        if item_id != item:
            raise error("CURRENT_ITEM_REQUIRED")
        # Skip navigates without erasing an already saved selection. Clearing uses draft [].
        if a.current_position == a.total - 1:
            await finalize_exam(db, a, "last_question")
            return
        a.current_position += 1
    elif operation == "abandon":
        a.status = "abandoned"
        a.finalized_at = await db.scalar(select(func.clock_timestamp()))
        a.finish_reason = "user_exit"
    else:
        raise error("EXAM_OPERATION_UNSUPPORTED", status=422)
    a.version += 1
    await db.flush()
    audit(
        db,
        actor=a.user_id,
        action="exam." + operation,
        entity_type="attempt",
        entity_id=a.id,
        request_id=UUID(request.state.request_id),
    )


async def review_items(db: AsyncSession, a: Attempt, offset: int, limit: int) -> dict[str, Any]:
    from app.attempts.service import error

    if a.mode != "exam" or a.status != "completed":
        raise error("RESULT_NOT_AVAILABLE")
    if offset < 0 or not 1 <= limit <= 100:
        raise error("INVALID_PAGE", status=422)
    items = (
        await db.scalars(
            select(AttemptItem)
            .where(AttemptItem.attempt_id == a.id)
            .order_by(AttemptItem.position)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    rows = []
    for item in items:
        data = await item_data(db, item)
        response = await db.get(AttemptResponse, item.id)
        revision = await db.get(QuestionRevision, item.revision_id)
        assert response is not None and revision is not None
        keys = (
            await db.scalars(
                select(QuestionOption.id)
                .join(AttemptOption, AttemptOption.option_id == QuestionOption.id)
                .where(AttemptOption.item_id == item.id, QuestionOption.is_correct.is_(True))
            )
        ).all()
        data.update(
            selected_option_ids=[str(response.selected_option_id)]
            if response.selected_option_id
            else [],
            is_correct=response.is_correct,
            correct_option_ids=[str(k) for k in keys],
        )
        if revision.explanation:
            data["explanation"] = revision.explanation
        rows.append(data)
    return {
        "items": rows,
        "total": a.total,
        "next_offset": offset + len(rows) if offset + len(rows) < a.total else None,
    }
