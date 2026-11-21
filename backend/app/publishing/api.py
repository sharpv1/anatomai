from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request, Response
from pydantic import Field, StringConstraints, field_validator, model_validator
from sqlalchemy import func, select

from app.admin.drafts import tag
from app.admin.models import StepUp
from app.admin.schemas import Body
from app.content.models import CatalogState
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.policy import access
from app.identity.schemas import Envelope
from app.identity.service import audit
from app.imports.api import get_job
from app.imports.models import ImportJob
from app.publishing.models import PublicationItem, PublicationRun
from app.publishing.service import command, direct, lock_catalog, owned_revision, stamp
from app.publishing.snapshots import digest, eligible, fail, snapshots, staging, verify_file

router = APIRouter(prefix="/api/v1/admin", tags=["explicit question publication"])
Idem = Annotated[UUID, Header(alias="Idempotency-Key")]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class Confirmation(Body):
    confirm: Literal[True]
    preview_hash: Hash

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit boolean true is required")
        return value


class ReasonConfirmation(Confirmation):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class ImportConfirmation(Confirmation):
    file_sha256: Hash
    template_version: Literal[1]
    selected_positions: Annotated[
        list[Annotated[int, Field(strict=True, ge=1, le=5000)]],
        Field(min_length=1, max_length=5000),
    ]

    @model_validator(mode="after")
    def distinct(self) -> "ImportConfirmation":
        if len(set(self.selected_positions)) != len(self.selected_positions):
            raise ValueError("Duplicate positions")
        self.selected_positions.sort()
        return self


@router.get(
    "/question-revisions/{revision_id}/publication-preview", response_model=Envelope[dict[str, Any]]
)
@access("content.publish")
async def revision_preview(revision_id: UUID, request: Request, response: Response) -> Any:
    await lock_catalog(current_db(request))
    await owned_revision(request, revision_id)
    snap = (await snapshots(current_db(request), [revision_id]))[revision_id]
    version = await current_db(request).scalar(
        select(CatalogState.version).where(CatalogState.id == 1)
    )
    assert version is not None
    response.headers["ETag"] = tag(version)
    return Envelope(
        data={
            "preview_hash": stamp(request, snap),
            "revision_id": revision_id,
            "state": snap,
            "publishable": eligible(snap),
        },
        meta=meta(request),
    )


@router.post("/question-revisions/{revision_id}/publish", response_model=Envelope[dict[str, Any]])
@access("content.publish")
async def publish(revision_id: UUID, body: Confirmation, key: Idem, request: Request) -> Any:
    return Envelope(
        data=await direct(request, revision_id, "publish", body, key), meta=meta(request)
    )


@router.post("/question-revisions/{revision_id}/withdraw", response_model=Envelope[dict[str, Any]])
@access("content.publish")
async def withdraw(revision_id: UUID, body: ReasonConfirmation, key: Idem, request: Request) -> Any:
    return Envelope(
        data=await direct(request, revision_id, "withdraw", body, key), meta=meta(request)
    )


@router.post("/question-revisions/{revision_id}/restore", response_model=Envelope[dict[str, Any]])
@access("content.publish")
async def restore(revision_id: UUID, body: ReasonConfirmation, key: Idem, request: Request) -> Any:
    return Envelope(
        data=await direct(request, revision_id, "restore", body, key), meta=meta(request)
    )


async def import_preview_data(
    request: Request, job: ImportJob
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[UUID, dict[str, Any]]]:
    if job.status != "completed":
        raise fail("IMPORT_NOT_READY", "Нужен завершённый импорт.")
    await verify_file(current_db(request), request.app.state.settings, job)
    stage_hash, refs = await staging(current_db(request), job)
    snaps = await snapshots(
        current_db(request), list({r["revision_id"] for r in refs if r["revision_id"]})
    )
    positions = []
    blocked = []
    conflicts = 0
    invalid = 0
    duplicates = 0
    for row in refs:
        snap = snaps.get(row["revision_id"])
        row["publishable"] = (
            not row["errors"]
            and row["action"] in ("create", "update", "unchanged")
            and snap is not None
            and snap["body_hash"] == row["fingerprint"] == row["payload_fingerprint"]
            and snap["question_id"] == str(row["question_id"])
            and eligible(snap)
        )
        if row["publishable"]:
            positions.append(row["position"])
        else:
            reason = (
                "ROW_ERROR"
                if row["errors"]
                else "DUPLICATE_OR_CONFLICT"
                if row["action"] not in ("create", "update", "unchanged")
                else "NO_REVISION"
                if snap is None
                else "REVISION_CHANGED"
                if snap["body_hash"] != row["fingerprint"]
                or row["payload_fingerprint"] != row["fingerprint"]
                else "NOT_PUBLISHABLE"
            )
            blocked.append({"position": row["position"], "code": reason})
            if reason == "REVISION_CHANGED":
                conflicts += 1
        conflicts += row["action"] == "conflict"
        invalid += row["errors"]
        duplicates += row["action"] in ("duplicate", "unchanged")
    history = [
        (str(run_id), status, attempts)
        for run_id, status, attempts in (
            await current_db(request).execute(
                select(PublicationRun.id, PublicationRun.status, PublicationRun.attempts)
                .where(PublicationRun.import_job_id == job.id)
                .order_by(PublicationRun.sequence)
            )
        ).all()
    ]
    preview_hash = digest(
        {
            "publication_history": history,
            "actor": current_identity(request).user.id,
            "staging_hash": stage_hash,
            "snapshots": {str(k): v for k, v in snaps.items()},
        }
    )
    return (
        {
            "import_job_id": str(job.id),
            "preview_hash": preview_hash,
            "staging_hash": stage_hash,
            "file_sha256": job.sha256,
            "template_version": job.template_version,
            "result_version": job.result_version,
            "found": len(refs),
            "valid": len(refs) - invalid,
            "errors": invalid,
            "conflicts": conflicts,
            "duplicates": duplicates,
            "publishable": len(positions),
            "eligible_positions": positions,
            "blocked": blocked,
            "hidden_parent_count": sum(
                r["publishable"] and not snaps[r["revision_id"]]["catalog_visible"] for r in refs
            ),
        },
        refs,
        snaps,
    )


@router.get("/imports/{job_id}/publication-preview", response_model=Envelope[dict[str, Any]])
@access("content.import.publish")
async def import_preview(job_id: UUID, request: Request, response: Response) -> Any:
    state = await lock_catalog(current_db(request))
    job = await get_job(request, job_id, lock=True)
    result, _, _ = await import_preview_data(request, job)
    response.headers["ETag"] = tag(state.version)
    return Envelope(data=result, meta=meta(request))


@router.post("/imports/{job_id}/publish", response_model=Envelope[dict[str, Any]])
@access("content.import.publish")
async def confirm_import(
    job_id: UUID, body: ImportConfirmation, key: Idem, request: Request
) -> Any:
    # Scope checked before replay too; import publishing is admin-only in the role matrix.
    await get_job(request, job_id)
    db = current_db(request)

    async def apply() -> dict[str, Any]:
        job = await get_job(request, job_id, lock=True)
        preview, refs, snaps = await import_preview_data(request, job)
        if (
            preview["preview_hash"] != body.preview_hash
            or body.file_sha256 != job.sha256
            or body.template_version != job.template_version
        ):
            raise fail("STALE_CONFIRMATION")
        if await db.scalar(
            select(PublicationRun.id).where(
                PublicationRun.import_job_id == job.id,
                PublicationRun.status.in_(["queued", "processing"]),
            )
        ):
            raise fail("PUBLICATION_ACTIVE")
        selected_set = set(body.selected_positions)
        selected = [r for r in refs if r["position"] in selected_set]
        if len(selected) != len(body.selected_positions) or any(
            not r["publishable"] for r in selected
        ):
            raise fail(
                "INVALID_SELECTION",
                "Выберите корректные single_choice без конфликтов и дубликатов.",
            )
        if len({r["question_id"] for r in selected}) != len(selected):
            raise fail("SELECTION_CONFLICT", "Выберите только одну редакцию каждого вопроса.")
        confirmation = digest({"preview": body.preview_hash, "selected": body.selected_positions})
        if await db.scalar(
            select(PublicationRun.id).where(
                PublicationRun.import_job_id == job.id,
                PublicationRun.confirmation_hash == confirmation,
            )
        ):
            raise fail("ALREADY_CONFIRMED")
        identity = current_identity(request)
        grant = await db.get(StepUp, identity.session.id)
        assert grant
        run = PublicationRun(
            id=uuid4(),
            import_job_id=job.id,
            confirmed_by=identity.user.id,
            authorized_session_id=identity.session.id,
            mfa_verified_at=grant.verified_at,
            confirmation_hash=confirmation,
            staging_hash=preview["staging_hash"],
            selection_hash=digest(body.selected_positions),
            selected_count=len(selected),
            file_sha256=job.sha256,
            template_version=job.template_version,
            result_version=job.result_version,
        )
        db.add(run)
        await db.flush()
        db.add_all(
            [
                PublicationItem(
                    run_id=run.id,
                    import_row_id=r["id"],
                    position=r["position"],
                    question_id=r["question_id"],
                    revision_id=r["revision_id"],
                    snapshot=snaps[r["revision_id"]],
                )
                for r in selected
            ]
        )
        await db.flush()
        audit(
            db,
            actor=identity.user.id,
            action="publication.confirmed",
            entity_type="publication_run",
            entity_id=run.id,
            request_id=UUID(request.state.request_id),
            details={"selected": len(selected), "excluded": len(refs) - len(selected)},
        )
        return {
            "publication_id": str(run.id),
            "status": "queued",
            "selected": len(selected),
            "excluded": len(refs) - len(selected),
        }

    return Envelope(
        data=await command(
            request,
            "import.publish",
            key,
            {"import_job_id": str(job_id), "body": body.model_dump(mode="json")},
            apply,
        ),
        meta=meta(request),
    )


async def run_for(request: Request, run_id: UUID, *, lock: bool = False) -> PublicationRun:
    run = await current_db(request).get(PublicationRun, run_id, with_for_update=lock)
    if run is None:
        raise fail("NOT_FOUND", "Публикация не найдена.", 404)
    return run


async def report(request: Request, run: PublicationRun) -> dict[str, Any]:
    rows = (
        await current_db(request).execute(
            select(PublicationItem.status, func.count())
            .where(PublicationItem.run_id == run.id)
            .group_by(PublicationItem.status)
        )
    ).all()
    counts = {"pending": 0, "published": 0, "unchanged": 0, "failed": 0}
    counts.update({status: count for status, count in rows})
    items = (
        (
            await current_db(request).execute(
                select(
                    PublicationItem.position,
                    PublicationItem.revision_id,
                    PublicationItem.status,
                    PublicationItem.error_code,
                )
                .where(PublicationItem.run_id == run.id)
                .order_by(PublicationItem.position)
            )
        )
        .mappings()
        .all()
    )
    return {
        "id": run.id,
        "import_job_id": run.import_job_id,
        "status": run.status,
        "attempts": run.attempts,
        "cancel_requested": run.cancel_requested,
        "error_code": run.error_code,
        "message": {
            "STALE_ITEM": "Редакция изменилась. Подтвердите актуальные вопросы заново.",
            "STAGING_CHANGED": "Содержимое набора изменилось. Нужен новый предпросмотр.",
            "SELECTION_CHANGED": "Подтверждённый выбор изменился. Публикация остановлена.",
            "FILE_CHANGED": "Исходный файл отсутствует или изменился.",
            "FILE_EXPIRED": "Истёк срок хранения исходного файла.",
            "ACCESS_REVOKED": "У подтвердившего пользователя больше нет доступа.",
            "PROCESSING_FAILED": "Сбой обработки. Уже опубликованные батчи сохранены.",
            "LEASE_EXHAUSTED": "Лимит перезапусков исчерпан. Нужен новый предпросмотр.",
        }.get(run.error_code or ""),
        "counts": counts,
        "current_catalog_version": await current_db(request).scalar(
            select(CatalogState.version).where(CatalogState.id == 1)
        ),
        "items": [dict(r) for r in items],
    }


@router.get("/publications/{run_id}", response_model=Envelope[dict[str, Any]])
@access("content.import.publish")
async def publication_report(run_id: UUID, request: Request) -> Any:
    return Envelope(data=await report(request, await run_for(request, run_id)), meta=meta(request))


@router.post("/publications/{run_id}/cancel", response_model=Envelope[dict[str, Any]])
@access("content.import.publish")
async def cancel_publication(run_id: UUID, request: Request) -> Any:
    run = await run_for(request, run_id, lock=True)
    if run.status in ("queued", "processing"):
        run.cancel_requested = True
        if run.status == "queued":
            run.status = "cancelled"
        audit(
            current_db(request),
            actor=current_identity(request).user.id,
            action="publication.cancel_requested",
            entity_type="publication_run",
            entity_id=run.id,
            request_id=UUID(request.state.request_id),
        )
    return Envelope(data=await report(request, run), meta=meta(request))


@router.post("/publications/{run_id}/retry", response_model=Envelope[dict[str, Any]])
@access("content.import.publish")
async def retry_publication(run_id: UUID, request: Request) -> Any:
    db = current_db(request)
    await lock_catalog(db)
    run = await run_for(request, run_id, lock=True)
    if run.status not in ("failed", "cancelled") or run.attempts >= 3:
        raise fail("PUBLICATION_STATE")
    if run.error_code not in (None, "PROCESSING_FAILED"):
        raise fail("RECONFIRM_REQUIRED")
    if await db.scalar(
        select(PublicationRun.id).where(
            PublicationRun.import_job_id == run.import_job_id,
            PublicationRun.sequence > run.sequence,
        )
    ):
        raise fail("RECONFIRM_REQUIRED")
    job = await db.get(ImportJob, run.import_job_id)
    assert job
    await verify_file(db, request.app.state.settings, job)
    stage_hash, _ = await staging(db, job)
    if stage_hash != run.staging_hash:
        raise fail("STAGING_CHANGED")
    run.status = "queued"
    run.cancel_requested = False
    run.error_code = None
    audit(
        db,
        actor=current_identity(request).user.id,
        action="publication.retried",
        entity_type="publication_run",
        entity_id=run.id,
        request_id=UUID(request.state.request_id),
    )
    return Envelope(data=await report(request, run), meta=meta(request))
