"""Canonical snapshots use actual content/options, never only the stored fingerprint."""

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import QuestionBody
from app.content.fingerprints import fingerprint
from app.content.models import (
    AccessPolicy,
    Asset,
    Category,
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.imports.limits import UPLOAD_BYTES
from app.imports.models import ImportJob, ImportRow
from app.imports.store import Store


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        ).encode()
    ).hexdigest()


def fail(
    code: str,
    message: str = "Данные изменились или не готовы. Обновите предпросмотр.",
    status: int = 409,
) -> ApplicationError:
    return ApplicationError(code, message, status)


async def verify_file(db: AsyncSession, settings: Settings, job: ImportJob) -> None:
    if job.raw_deleted_at is not None:
        raise fail("FILE_EXPIRED", "Исходный файл больше не хранится. Загрузите новый файл.")
    asset = await db.get(Asset, job.asset_id)
    if asset is None or asset.sha256 != job.sha256 or not 0 < asset.byte_size <= UPLOAD_BYTES:
        raise fail("FILE_CHANGED")
    path = Store(settings).path(asset.storage_key)

    def check() -> bool:
        try:
            if not path.is_file() or path.stat().st_size != asset.byte_size:
                return False
            h = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                while chunk := source.read(65536):
                    size += len(chunk)
                    if size > asset.byte_size:
                        return False
                    h.update(chunk)
            return size == asset.byte_size and h.hexdigest() == job.sha256
        except OSError:
            return False

    if not await asyncio.to_thread(check):
        raise fail("FILE_CHANGED", "Исходный файл отсутствует или изменился.")


def body_from(rev: QuestionRevision, options: list[QuestionOption]) -> QuestionBody:
    return QuestionBody(
        kind=rev.kind,
        text=rev.text,
        explanation=rev.explanation,
        source_id=rev.source_id,
        source_reference=rev.source_reference,
        source_page=rev.source_page,
        license_reference=rev.license_reference,
        options=[{"code": o.code, "text": o.text, "is_correct": o.is_correct} for o in options],
    )


async def snapshots(db: AsyncSession, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    revisions = list(
        (
            await db.scalars(
                select(QuestionRevision)
                .where(QuestionRevision.id.in_(ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    qids = list({r.question_id for r in revisions})
    questions = {
        q.id: q
        for q in (
            await db.scalars(
                select(Question)
                .where(Question.id.in_(qids))
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    latest: dict[UUID, int] = {
        key: value
        for key, value in (
            (
                await db.execute(
                    select(QuestionRevision.question_id, func.max(QuestionRevision.revision_number))
                    .where(QuestionRevision.question_id.in_(qids))
                    .group_by(QuestionRevision.question_id)
                )
            ).all()
        )
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
    parents: dict[UUID, list[dict[str, Any]]] = {}
    query = (
        select(
            TopicQuestion.question_id,
            TopicQuestion.topic_id,
            TopicQuestion.position,
            Topic.status.label("topic_status"),
            Topic.title.label("topic_title"),
            Topic.slug.label("topic_slug"),
            Discipline.title.label("discipline_title"),
            Discipline.slug.label("discipline_slug"),
            Category.title.label("category_title"),
            Discipline.id.label("discipline_id"),
            Discipline.status.label("discipline_status"),
            Category.id.label("category_id"),
            Category.status.label("category_status"),
            Topic.access_policy_id,
            AccessPolicy.status.label("policy_status"),
            AccessPolicy.requirement,
        )
        .join(Topic, Topic.id == TopicQuestion.topic_id)
        .join(Discipline, Discipline.id == Topic.discipline_id)
        .outerjoin(Category, Category.id == Topic.category_id)
        .outerjoin(AccessPolicy, AccessPolicy.id == Topic.access_policy_id)
        .where(TopicQuestion.question_id.in_(qids))
        .order_by(TopicQuestion.question_id, TopicQuestion.topic_id)
    )
    for row in (await db.execute(query)).mappings():
        parents.setdefault(row["question_id"], []).append(
            {k: str(v) if isinstance(v, UUID) else v for k, v in row.items() if k != "question_id"}
        )
    result = {}
    for rev in revisions:
        q = questions[rev.question_id]
        opts = options.get(rev.id, [])
        try:
            body = body_from(rev, opts)
            body_hash = fingerprint(body)
            structural = body.kind == "single_choice"
        except ValidationError:
            body_hash = digest(
                {
                    "kind": rev.kind,
                    "text": rev.text,
                    "options": [(o.id, o.text, o.is_correct) for o in opts],
                }
            )
            structural = False
        ps = parents.get(q.id, [])
        available = bool(ps) and all(
            p["topic_status"] != "withdrawn"
            and p["discipline_status"] != "withdrawn"
            and p["category_status"] != "withdrawn"
            for p in ps
        )
        result[rev.id] = {
            "revision_id": str(rev.id),
            "question_id": str(q.id),
            "revision_number": rev.revision_number,
            "status": rev.status,
            "created_by": str(rev.created_by) if rev.created_by else None,
            "body_hash": body_hash,
            "raw_hash": digest(
                {
                    "revision": {col.name: getattr(rev, col.name) for col in rev.__table__.columns},
                    "question": {col.name: getattr(q, col.name) for col in q.__table__.columns},
                    "options": [
                        {col.name: getattr(o, col.name) for col in o.__table__.columns}
                        for o in opts
                    ],
                }
            ),
            "option_ids": [str(o.id) for o in opts],
            "parents": ps,
            "current_revision_id": str(q.current_revision_id) if q.current_revision_id else None,
            "latest_revision_number": latest[q.id],
            "archived_at": q.archived_at.isoformat() if q.archived_at else None,
            "structural": structural,
            "parents_available": available,
            "catalog_visible": available
            and any(
                p["topic_status"] == p["discipline_status"] == "published"
                and p["category_status"] in (None, "published")
                and (
                    p["access_policy_id"] is None
                    or (p["policy_status"] == "published" and p["requirement"] == "authenticated")
                )
                for p in ps
            ),
        }
    return result


def eligible(snapshot: dict[str, Any]) -> bool:
    return (
        snapshot["structural"]
        and snapshot["parents_available"]
        and not snapshot["archived_at"]
        and (
            (
                snapshot["status"] == "draft"
                and snapshot["revision_number"] == snapshot["latest_revision_number"]
            )
            or (
                snapshot["status"] == "published"
                and snapshot["current_revision_id"] == snapshot["revision_id"]
            )
        )
    )


async def staging(db: AsyncSession, job: ImportJob) -> tuple[str, list[dict[str, Any]]]:
    h = hashlib.sha256()
    h.update(
        digest(
            {
                k: getattr(job, k)
                for k in (
                    "id",
                    "asset_id",
                    "sha256",
                    "file_format",
                    "template_version",
                    "result_version",
                    "status",
                    "found",
                    "valid_count",
                    "error_count",
                    "duplicate_count",
                    "applied_count",
                )
            }
        ).encode()
    )
    refs = []
    async for row in await db.stream_scalars(
        select(ImportRow)
        .where(ImportRow.import_job_id == job.id)
        .order_by(ImportRow.position)
        .execution_options(yield_per=100)
    ):
        h.update(
            digest(
                {
                    k: getattr(row, k)
                    for k in (
                        "id",
                        "position",
                        "location",
                        "discipline",
                        "topic",
                        "external_key",
                        "generated_key",
                        "fingerprint",
                        "content_hash",
                        "normalized_payload",
                        "errors",
                        "warnings",
                        "action",
                        "topic_id",
                        "target_question_id",
                        "applied_revision_id",
                    )
                }
            ).encode()
        )
        try:
            payload_fingerprint = fingerprint(QuestionBody.model_validate(row.normalized_payload))
        except ValidationError:
            payload_fingerprint = None
        refs.append(
            {
                "id": row.id,
                "position": row.position,
                "revision_id": row.applied_revision_id,
                "question_id": row.target_question_id,
                "fingerprint": row.fingerprint,
                "payload_fingerprint": payload_fingerprint,
                "errors": bool(row.errors),
                "action": row.action,
            }
        )
    return h.hexdigest(), refs
