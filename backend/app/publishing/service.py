from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.drafts import write_guard
from app.content.models import CatalogState, Question, QuestionOption, QuestionRevision
from app.core.idempotency import StoredResponse, request_fingerprint, run_idempotent
from app.identity.dependencies import current_db, current_identity
from app.identity.service import audit
from app.publishing.models import PublicationCommand
from app.publishing.snapshots import body_from, digest, eligible, fail, snapshots


def publisher(request: Request) -> None:
    if not current_identity(request).roles.intersection({"admin", "content_editor"}):
        raise fail("ACCESS_DENIED", "Публикация доступна редактору и администратору.", 403)


async def owned_revision(request: Request, revision_id: UUID) -> QuestionRevision:
    publisher(request)
    rev = await current_db(request).get(QuestionRevision, revision_id, populate_existing=True)
    if rev is None or (
        "admin" not in current_identity(request).roles
        and rev.created_by != current_identity(request).user.id
    ):
        raise fail("NOT_FOUND", "Редакция не найдена.", 404)
    return rev


def stamp(request: Request, snapshot: dict[str, Any]) -> str:
    return digest({"actor": current_identity(request).user.id, "snapshot": snapshot})


async def lock_catalog(db: AsyncSession) -> CatalogState:
    state = await db.get(CatalogState, 1, with_for_update=True)
    if state is None:
        raise fail("SERVICE_NOT_READY", status=503)
    return state


async def command(
    request: Request, operation: str, key: UUID, payload: Any, action: Any
) -> dict[str, Any]:
    db = current_db(request)
    actor = current_identity(request).user.id

    async def apply(session: AsyncSession) -> StoredResponse:
        old = await session.scalar(
            select(PublicationCommand).where(
                PublicationCommand.actor_id == actor,
                PublicationCommand.operation == operation,
                PublicationCommand.key == key,
            )
        )
        reqhash = request_fingerprint(payload)
        if old:
            if old.request_hash != reqhash:
                raise fail("IDEMPOTENCY_KEY_REUSED", "Ключ использован для другого запроса.")
            return StoredResponse(200, old.result)
        await write_guard(request)
        result = await action()
        session.add(
            PublicationCommand(
                actor_id=actor, operation=operation, key=key, request_hash=reqhash, result=result
            )
        )
        await session.flush()
        return StoredResponse(200, result)

    response = await run_idempotent(
        db, actor_id=actor, operation=operation, key=key, payload=payload, action=apply
    )
    return cast(dict[str, Any], response.response.body)


async def publish_one(db: AsyncSession, revision_id: UUID, actor: UUID, request_id: UUID) -> str:
    rev = await db.get(QuestionRevision, revision_id, with_for_update=True)
    assert rev is not None
    q = await db.get(Question, rev.question_id, with_for_update=True)
    assert q is not None
    if rev.status == "published" and q.current_revision_id == rev.id:
        return "unchanged"
    if rev.status != "draft":
        raise fail("REVISION_STATE")
    rev.status = "published"
    await db.flush()
    q.current_revision_id = rev.id
    await db.flush()
    audit(
        db,
        actor=actor,
        action="question.published",
        entity_type="question_revision",
        entity_id=rev.id,
        request_id=request_id,
    )
    return "published"


async def direct(
    request: Request, revision_id: UUID, operation: str, body: Any, key: UUID
) -> dict[str, Any]:
    rev = await owned_revision(request, revision_id)
    db = current_db(request)

    async def apply() -> dict[str, Any]:
        await owned_revision(request, revision_id)
        snap = (await snapshots(db, [revision_id]))[revision_id]
        if stamp(request, snap) != body.preview_hash:
            raise fail("STALE_CONFIRMATION")
        actor = current_identity(request).user.id
        rid = UUID(request.state.request_id)
        target = revision_id
        if operation == "publish":
            if not eligible(snap):
                raise fail(
                    "NOT_PUBLISHABLE",
                    "Нужен актуальный корректный single_choice draft и доступные связи темы.",
                )
            outcome = await publish_one(db, revision_id, actor, rid)
        elif operation == "withdraw":
            if rev.status not in ("published", "withdrawn"):
                raise fail("REVISION_STATE")
            outcome = "unchanged"
            if rev.status == "published":
                rev.status = "withdrawn"
                await db.flush()
                outcome = "withdrawn"
                audit(
                    db,
                    actor=actor,
                    action="question.withdrawn",
                    entity_type="question_revision",
                    entity_id=rev.id,
                    request_id=rid,
                    details={"reason": body.reason},
                )
        else:
            if (
                rev.status not in ("published", "withdrawn")
                or not snap["structural"]
                or not snap["parents_available"]
                or snap["archived_at"]
            ):
                raise fail("NOT_RESTORABLE")
            q = await db.get(Question, rev.question_id, with_for_update=True)
            assert q is not None
            current = (
                (await snapshots(db, [q.current_revision_id])).get(q.current_revision_id)
                if q.current_revision_id
                else None
            )
            if (
                rev.status == "withdrawn"
                and current is not None
                and current["status"] == "published"
                and current["body_hash"] == snap["body_hash"]
            ):
                assert q.current_revision_id is not None
                target = q.current_revision_id
                outcome = "unchanged"
            elif rev.status == "published":
                outcome = "unchanged" if q.current_revision_id == rev.id else "restored"
                q.current_revision_id = rev.id
                await db.flush()
            else:
                opts = list(
                    (
                        await db.scalars(
                            select(QuestionOption)
                            .where(QuestionOption.revision_id == rev.id)
                            .order_by(QuestionOption.position)
                        )
                    ).all()
                )
                data = body_from(rev, opts)
                number = (
                    await db.scalar(
                        select(func.max(QuestionRevision.revision_number)).where(
                            QuestionRevision.question_id == q.id
                        )
                    )
                    or 0
                ) + 1
                copy = QuestionRevision(
                    id=uuid4(),
                    question_id=q.id,
                    revision_number=number,
                    created_by=actor,
                    fingerprint=snap["body_hash"],
                    **data.model_dump(exclude={"options"}),
                )
                db.add(copy)
                await db.flush()
                db.add_all(
                    [
                        QuestionOption(
                            id=uuid4(),
                            revision_id=copy.id,
                            position=i,
                            code=o.code,
                            text=o.text,
                            is_correct=o.is_correct,
                        )
                        for i, o in enumerate(opts)
                    ]
                )
                await db.flush()
                target = copy.id
                await publish_one(db, copy.id, actor, rid)
                outcome = "restored_copy"
            if outcome != "unchanged":
                audit(
                    db,
                    actor=actor,
                    action="question.restored",
                    entity_type="question_revision",
                    entity_id=target,
                    request_id=rid,
                    details={"source_revision_id": str(rev.id), "reason": body.reason},
                )
        await db.flush()
        version = await db.scalar(select(CatalogState.version).where(CatalogState.id == 1))
        return {
            "revision_id": str(target),
            "question_id": str(rev.question_id),
            "outcome": outcome,
            "catalog_version": version,
        }

    return await command(
        request,
        "question." + operation,
        key,
        {"revision_id": str(revision_id), "body": body.model_dump(mode="json")},
        apply,
    )
