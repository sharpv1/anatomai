import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.admin.models import StepUp
from app.content.api import Cursor, Limit
from app.content.cursors import decode_cursor, encode_cursor, filter_hash
from app.content.models import Asset
from app.core.errors import ApplicationError
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.policy import access
from app.identity.schemas import Envelope
from app.identity.service import audit
from app.imports.errors import MESSAGES, issue
from app.imports.limits import MAX_ATTEMPTS, MIMES
from app.imports.models import ImportJob, ImportRow
from app.imports.store import Store
from app.imports.templates import document

router = APIRouter(prefix="/api/v1/admin", tags=["draft imports"])
Format = Literal["xlsx", "docx"]


def scope(request: Request, statement: Any) -> Any:
    identity = current_identity(request)
    return (
        statement
        if "admin" in identity.roles
        else statement.where(ImportJob.created_by == identity.user.id)
    )


async def get_job(request: Request, job_id: UUID, *, lock: bool = False) -> ImportJob:
    statement = scope(request, select(ImportJob).where(ImportJob.id == job_id))
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    job = await current_db(request).scalar(statement)
    if job is None:
        raise ApplicationError("NOT_FOUND", "Задание не найдено.", 404)
    return cast(ImportJob, job)


def data(job: ImportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "phase": job.phase,
        "format": job.file_format,
        "found": job.found,
        "valid": job.valid_count,
        "errors": job.error_count,
        "possible_duplicates": job.duplicate_count,
        "drafts_created": job.applied_count,
        "cancel_requested": job.cancel_requested,
        "attempts": job.attempts,
        "result_version": job.result_version,
        "file_sha256": job.sha256,
        "error_code": job.error_code,
        "message": MESSAGES.get(job.error_code or ""),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "publication_available": job.status == "completed",
    }


def key(request: Request) -> str:
    secret = request.app.state.settings.content_cursor_signing_key
    if secret is None:
        raise ApplicationError("CONTENT_NOT_CONFIGURED", "Курсоры не настроены.", 503)
    return str(secret.get_secret_value())


@router.get("/import-templates/{file_format}")
@access("content.import.manage")
async def template(file_format: Format) -> Response:
    return Response(
        content=document(file_format),
        media_type=MIMES[file_format],
        headers={"Content-Disposition": f'attachment; filename="medexa-import-v1.{file_format}"'},
    )


@router.post(
    "/imports",
    status_code=201,
    response_model=Envelope[dict[str, Any]],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in (*MIMES.values(), "application/octet-stream")
            },
        }
    },
)
@access("content.import.manage")
async def upload(
    request: Request, response: Response, file_format: Annotated[Format, Query(alias="format")]
) -> Any:
    store = Store(request.app.state.settings)
    mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if mime not in (MIMES[file_format], "application/octet-stream"):
        raise ApplicationError(
            "FILE_FORMAT", "Отправьте XLSX/DOCX как бинарный файл, без multipart/JSON.", 415
        )
    db = current_db(request)
    identity = current_identity(request)
    active = await db.scalar(
        select(func.count())
        .select_from(ImportJob)
        .where(
            ImportJob.created_by == identity.user.id, ImportJob.status.in_(["queued", "processing"])
        )
    )
    if (active or 0) >= 3:
        raise ApplicationError("IMPORT_QUEUE_FULL", "Дождитесь завершения текущих загрузок.", 429)
    used = await db.scalar(
        select(func.coalesce(func.sum(Asset.byte_size), 0))
        .join(ImportJob, ImportJob.asset_id == Asset.id)
        .where(ImportJob.created_by == identity.user.id, ImportJob.raw_deleted_at.is_(None))
    )
    used = int(used or 0)
    if used >= 100 * 1024 * 1024:
        raise ApplicationError("IMPORT_QUOTA", "Достигнут лимит хранения исходных файлов.", 429)
    storage_key, digest, size = await store.upload(request)
    request.state.import_pending_paths = [str(store.path(storage_key))]
    existing = await db.scalar(
        select(ImportJob).where(
            ImportJob.created_by == identity.user.id,
            ImportJob.sha256 == digest,
            ImportJob.file_format == file_format,
            ImportJob.template_version == 1,
        )
    )
    if existing is not None:
        store.path(storage_key).unlink()
        request.state.import_pending_paths = []
        response.status_code = 200
        return Envelope(data={**data(existing), "reused": True}, meta=meta(request))
    if used + size > 100 * 1024 * 1024:
        raise ApplicationError("IMPORT_QUOTA", "Достигнут лимит хранения файлов.", 429)
    asset = Asset(
        id=UUID(storage_key),
        storage_key=storage_key,
        sha256=digest,
        media_type=MIMES[file_format],
        byte_size=size,
        status="draft",
        created_by=identity.user.id,
    )
    db.add(asset)
    await db.flush()
    grant = await db.get(StepUp, identity.session.id)
    assert grant is not None
    job = ImportJob(
        id=uuid4(),
        asset_id=asset.id,
        created_by=identity.user.id,
        authorized_session_id=identity.session.id,
        mfa_verified_at=grant.verified_at,
        sha256=digest,
        file_format=file_format,
    )
    db.add(job)
    await db.flush()
    audit(
        db,
        actor=identity.user.id,
        action="import.queued",
        entity_type="import_job",
        entity_id=job.id,
        request_id=UUID(request.state.request_id),
    )
    return Envelope(data={**data(job), "reused": False}, meta=meta(request))


@router.get("/imports", response_model=Envelope[dict[str, Any]])
@access("content.import.manage")
async def jobs(request: Request, limit: Limit = 20, cursor: Cursor = None) -> Any:
    statement = scope(request, select(ImportJob))
    fingerprint = filter_hash(
        {
            "scope": "imports",
            "owner": str(current_identity(request).user.id),
            "roles": "|".join(sorted(current_identity(request).roles)),
        }
    )
    if cursor:
        position, _ = decode_cursor(cursor, key(request), version=1, scope=fingerprint)
        statement = statement.where(ImportJob.sequence < position)
    rows = list(
        (
            await current_db(request).scalars(
                statement.order_by(ImportJob.sequence.desc()).limit(limit + 1)
            )
        ).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        encode_cursor(
            key(request),
            version=1,
            scope=fingerprint,
            position=rows[-1].sequence,
            entity_id=str(rows[-1].id),
        )
        if more
        else None
    )
    return Envelope(
        data={
            "items": [data(row) for row in rows],
            "page": {"next_cursor": next_cursor, "has_more": more},
        },
        meta=meta(request),
    )


@router.get("/imports/{job_id}", response_model=Envelope[dict[str, Any]])
@access("content.import.manage")
async def detail(job_id: UUID, request: Request) -> Any:
    return Envelope(data=data(await get_job(request, job_id)), meta=meta(request))


@router.post("/imports/{job_id}/cancel", response_model=Envelope[dict[str, Any]])
@access("content.import.manage")
async def cancel(job_id: UUID, request: Request) -> Any:
    job = await get_job(request, job_id, lock=True)
    if job.status in ("queued", "processing"):
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
            job.phase = "done"
        job.updated_at = datetime.now(UTC)
        audit(
            current_db(request),
            actor=current_identity(request).user.id,
            action="import.cancel.requested" if job.status == "processing" else "import.cancelled",
            entity_type="import_job",
            entity_id=job.id,
            request_id=UUID(request.state.request_id),
        )
    return Envelope(data=data(job), meta=meta(request))


@router.post("/imports/{job_id}/retry", response_model=Envelope[dict[str, Any]])
@access("content.import.manage")
async def retry(job_id: UUID, request: Request) -> Any:
    job = await get_job(request, job_id, lock=True)
    if job.status not in ("failed", "cancelled", "completed") or (
        job.status == "completed" and job.error_count == 0
    ):
        raise ApplicationError("IMPORT_STATE", "Задание нельзя повторить в этом состоянии.", 409)
    if job.attempts >= MAX_ATTEMPTS:
        raise ApplicationError(
            "IMPORT_ATTEMPTS",
            "Лимит повторов исчерпан. Сохраните исправленный файл и загрузите заново.",
            409,
        )
    if job.raw_deleted_at is not None:
        raise ApplicationError("FILE_EXPIRED", MESSAGES["FILE_EXPIRED"], 409)
    from app.publishing.models import PublicationRun

    if await current_db(request).scalar(
        select(PublicationRun.id).where(PublicationRun.import_job_id == job.id).limit(1)
    ):
        raise ApplicationError("IMPORT_FROZEN", "Набор уже подтверждён для публикации.", 409)
    job.status = "queued"
    job.phase = "queued"
    job.cancel_requested = False
    job.error_code = None
    job.result_version += 1
    job.updated_at = datetime.now(UTC)
    audit(
        current_db(request),
        actor=current_identity(request).user.id,
        action="import.retried",
        entity_type="import_job",
        entity_id=job.id,
        request_id=UUID(request.state.request_id),
    )
    return Envelope(data=data(job), meta=meta(request))


async def terminal(request: Request, job_id: UUID) -> ImportJob:
    job = await get_job(request, job_id)
    if job.status in ("queued", "processing"):
        raise ApplicationError(
            "IMPORT_PROCESSING", "Отчёт станет доступен после завершения или отмены обработки.", 409
        )
    return job


def row_data(row: ImportRow) -> dict[str, Any]:
    return {
        "position": row.position,
        "location": row.location,
        "discipline": row.discipline,
        "topic": row.topic,
        "external_id": row.external_key,
        "generated_id": row.generated_key,
        "action": row.action,
        "question": str(row.normalized_payload.get("text", ""))[:300],
        "errors": [issue(str(code)) for code in row.errors],
        "warnings": [issue(str(code)) for code in row.warnings],
        "draft_revision_id": row.applied_revision_id,
    }


@router.get("/imports/{job_id}/rows", response_model=Envelope[dict[str, Any]])
@access("content.import.manage")
async def rows(job_id: UUID, request: Request, limit: Limit = 30, cursor: Cursor = None) -> Any:
    job = await terminal(request, job_id)
    fingerprint = filter_hash(
        {
            "scope": "import-rows",
            "job": str(job.id),
            "owner": str(current_identity(request).user.id),
        }
    )
    after = 0
    if cursor:
        try:
            after, _ = decode_cursor(
                cursor, key(request), version=job.result_version, scope=fingerprint
            )
        except ApplicationError as exc:
            if exc.code == "CATALOG_CHANGED":
                raise ApplicationError(
                    "IMPORT_CHANGED", "Задание повторено. Обновите отчёт.", 409
                ) from None
            raise
    items = list(
        (
            await current_db(request).scalars(
                select(ImportRow)
                .where(ImportRow.import_job_id == job.id, ImportRow.position > after)
                .order_by(ImportRow.position)
                .limit(limit + 1)
            )
        ).all()
    )
    more = len(items) > limit
    items = items[:limit]
    next_cursor = (
        encode_cursor(
            key(request),
            version=job.result_version,
            scope=fingerprint,
            position=items[-1].position,
            entity_id=str(items[-1].id),
        )
        if more
        else None
    )
    return Envelope(
        data={
            "items": [row_data(row) for row in items],
            "page": {"next_cursor": next_cursor, "has_more": more},
        },
        meta=meta(request),
    )


def csv_safe(value: object) -> str:
    text = str(value or "")
    stripped = text.lstrip("\ufeff" + "".join(chr(i) for i in range(33)))
    if stripped.startswith(("=", "+", "-", "@")) or (text and ord(text[0]) < 32):
        return "'" + text
    return text


@router.get("/imports/{job_id}/report")
@access("content.import.manage")
async def report(job_id: UUID, request: Request) -> StreamingResponse:
    job = await terminal(request, job_id)
    # Select bounded report columns only; do not load 5000 full 64KiB payloads.
    entries = (
        (
            await current_db(request).execute(
                select(
                    ImportRow.position,
                    ImportRow.location,
                    ImportRow.discipline,
                    ImportRow.topic,
                    ImportRow.external_key,
                    ImportRow.action,
                    ImportRow.errors,
                    ImportRow.warnings,
                )
                .where(ImportRow.import_job_id == job.id)
                .order_by(ImportRow.position)
                .limit(5000)
            )
        )
        .mappings()
        .all()
    )

    def chunks() -> Iterator[str]:
        yield "\ufeff"
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(
            [
                "Номер",
                "Строка/таблица",
                "Дисциплина",
                "Тема",
                "ID",
                "Действие",
                "Ошибки",
                "Предупреждения",
            ]
        )
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in entries:
            writer.writerow(
                [
                    csv_safe(
                        "; ".join(issue(str(code))["message"] for code in row[name])
                        if name in ("errors", "warnings")
                        else row[name]
                    )
                    for name in (
                        "position",
                        "location",
                        "discipline",
                        "topic",
                        "external_key",
                        "action",
                        "errors",
                        "warnings",
                    )
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        chunks(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="medexa-import-{job.id}.csv"',
            "Cache-Control": "no-store",
        },
    )
