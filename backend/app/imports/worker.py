"""Single DB-backed worker with leases, fencing and resumable draft-only batches."""

import argparse
import asyncio
import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import QuestionBody
from app.content.cursors import normalize
from app.content.fingerprints import content_hash, fingerprint
from app.content.models import (
    Asset,
    CatalogState,
    Category,
    ContentSource,
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.database import Database
from app.identity.models import User, UserRole
from app.identity.policy import ROLE_PERMISSIONS
from app.identity.service import audit
from app.imports.errors import ImportFileError
from app.imports.limits import BATCH, LEASE_SECONDS, MAX_ATTEMPTS, ROW_BYTES
from app.imports.models import ImportContentKey, ImportJob, ImportRow
from app.imports.runner import run_parser
from app.imports.store import Store

logger = logging.getLogger(__name__)
WORKER_LOCK = 72634012062


def now() -> datetime:
    return datetime.now(UTC)


class LeaseLost(Exception):
    pass


class Cancelled(Exception):
    pass


class Worker:
    def __init__(self, settings: Settings, *, database: Database | None = None) -> None:
        self.settings = settings
        self.database = database or Database(settings.model_copy(update={"db_pool_size": 2}))
        self.store = Store(settings)
        self.lock_connection: Any = None

    async def close(self) -> None:
        await self.database.dispose()

    async def claim(self) -> tuple[UUID, UUID] | None:
        async with self.database.sessions.begin() as db:
            job = await db.scalar(
                select(ImportJob)
                .where(
                    or_(
                        ImportJob.status == "queued",
                        and_(ImportJob.status == "processing", ImportJob.lease_until < now()),
                    )
                )
                .order_by(ImportJob.sequence)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            if job.cancel_requested or job.attempts >= MAX_ATTEMPTS:
                job.status = "cancelled" if job.cancel_requested else "failed"
                job.error_code = None if job.cancel_requested else "LEASE_EXHAUSTED"
                job.phase = "done"
                job.lease_token = None
                job.lease_until = None
                job.updated_at = now()
                return None
            job.status = "processing"
            job.phase = "parsing"
            job.attempts += 1
            job.lease_token = uuid4()
            job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            job.updated_at = now()
            job.error_code = None
            return job.id, job.lease_token

    async def fenced(self, db: AsyncSession, job_id: UUID, token: UUID) -> ImportJob:
        job = await db.get(ImportJob, job_id, with_for_update=True)
        if (
            job is None
            or job.status != "processing"
            or job.lease_token != token
            or job.lease_until is None
            or job.lease_until <= now()
        ):
            raise LeaseLost
        if job.cancel_requested:
            raise Cancelled
        return job

    async def heartbeat(self, job_id: UUID, token: UUID) -> None:
        if self.lock_connection is not None:
            await self.lock_connection.execute(text("SELECT 1"))
            await self.lock_connection.commit()
        async with self.database.sessions.begin() as db:
            job = await self.fenced(db, job_id, token)
            job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            job.updated_at = now()

    async def actor(self, db: AsyncSession, actor_id: UUID) -> set[str]:
        user = await db.get(User, actor_id, with_for_update=True)
        roles = set(
            (await db.scalars(select(UserRole.role_code).where(UserRole.user_id == actor_id))).all()
        )
        allowed = set().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in roles))
        if user is None or user.status != "active" or "content.import.manage" not in allowed:
            raise ImportFileError("ACCESS_REVOKED")
        return roles

    async def resolve(
        self, db: AsyncSession, row: dict[str, Any], actor_id: UUID, roles: set[str]
    ) -> tuple[UUID | None, list[str]]:
        if row["errors"]:
            return None, list(row["errors"])
        dkey = normalize(row["discipline"])
        tkey = normalize(row["topic"])
        ds = list(
            (
                await db.scalars(
                    select(Discipline).where(
                        Discipline.status != "withdrawn",
                        or_(Discipline.slug == dkey, Discipline.normalized_search_text == dkey),
                    )
                )
            ).all()
        )
        if len(ds) != 1:
            return None, ["UNKNOWN_DISCIPLINE" if not ds else "AMBIGUOUS_DISCIPLINE"]
        ts = list(
            (
                await db.scalars(
                    select(Topic).where(
                        Topic.discipline_id == ds[0].id,
                        Topic.status != "withdrawn",
                        or_(Topic.slug == tkey, Topic.normalized_search_text == tkey),
                    )
                )
            ).all()
        )
        if len(ts) != 1:
            return None, ["UNKNOWN_TOPIC" if not ts else "AMBIGUOUS_TOPIC"]
        body = QuestionBody.model_validate(row["payload"])
        if body.source_id:
            source = await db.get(ContentSource, body.source_id)
            if (
                source is None
                or source.status == "withdrawn"
                or (
                    "admin" not in roles
                    and source.created_by != actor_id
                    and source.status != "published"
                )
            ):
                return None, ["SOURCE_NOT_AVAILABLE"]
        return ts[0].id, []

    async def summarize(self, db: AsyncSession, job: ImportJob) -> None:
        rows = (
            await db.execute(
                select(
                    ImportRow.action,
                    ImportRow.errors,
                    ImportRow.warnings,
                    ImportRow.applied_revision_id,
                ).where(ImportRow.import_job_id == job.id)
            )
        ).all()
        job.valid_count = sum(not errors for _, errors, _, _ in rows)
        job.error_count = sum(bool(errors) for _, errors, _, _ in rows)
        job.duplicate_count = sum(
            action in ("duplicate", "unchanged") or "POSSIBLE_DUPLICATE" in warnings
            for action, _, warnings, _ in rows
        )
        job.applied_count = sum(
            rid is not None and action in ("create", "update") for action, _, _, rid in rows
        )
        job.updated_at = now()

    async def stage(self, job_id: UUID, token: UUID, output: Path, found: int) -> None:
        with output.open(encoding="utf-8") as file:
            while True:
                batch = []
                for _ in range(BATCH):
                    line = file.readline(ROW_BYTES + 1)
                    if not line:
                        break
                    if len(line.encode()) > ROW_BYTES:
                        raise ImportFileError("PARSER_LIMIT")
                    batch.append(json.loads(line))
                if not batch:
                    break
                async with self.database.sessions.begin() as db:
                    # Read actor id without locking job, then follow user -> job lock order.
                    owner = await db.scalar(
                        select(ImportJob.created_by).where(ImportJob.id == job_id)
                    )
                    if owner is None:
                        raise LeaseLost
                    roles = await self.actor(db, owner)
                    job = await self.fenced(db, job_id, token)
                    job.phase = "staging"
                    job.found = found
                    for raw in batch:
                        rid = uuid5(job.id, "row:" + str(raw["position"]))
                        row = await db.get(ImportRow, rid)
                        if row is not None and row.applied_revision_id is not None:
                            continue
                        topic_id, errors = await self.resolve(db, raw, job.created_by, roles)
                        if row is None:
                            row = ImportRow(id=rid, import_job_id=job.id, position=raw["position"])
                            db.add(row)
                        row.location = raw["location"]
                        row.discipline = raw["discipline"]
                        row.topic = raw["topic"]
                        row.external_key = raw["external_key"]
                        row.generated_key = raw["generated_key"]
                        row.fingerprint = raw["fingerprint"]
                        row.content_hash = raw["content_hash"]
                        row.normalized_payload = raw["payload"]
                        row.errors = [str(error) for error in errors]
                        row.warnings = raw["warnings"]
                        row.topic_id = topic_id
                        row.action = "error" if errors else "pending"
                    await db.flush()
                    await self.summarize(db, job)
                    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
                await self.heartbeat(job_id, token)
        async with self.database.sessions.begin() as db:
            job = await self.fenced(db, job_id, token)
            conflicts = (
                await db.execute(
                    select(ImportRow.topic_id, ImportRow.external_key)
                    .where(
                        ImportRow.import_job_id == job_id,
                        func.jsonb_array_length(ImportRow.errors) == 0,
                    )
                    .group_by(ImportRow.topic_id, ImportRow.external_key)
                    .having(func.count(func.distinct(ImportRow.fingerprint)) > 1)
                )
            ).all()
            for topic, key in conflicts:
                for row in (
                    await db.scalars(
                        select(ImportRow).where(
                            ImportRow.import_job_id == job_id,
                            ImportRow.topic_id == topic,
                            ImportRow.external_key == key,
                            ImportRow.applied_revision_id.is_(None),
                        )
                    )
                ).all():
                    row.errors = ["CONFLICTING_FILE_KEY"]
                    row.action = "conflict"
            await db.flush()
            await self.summarize(db, job)

    async def visible_latest(
        self, db: AsyncSession, q: Question, actor: UUID, roles: set[str]
    ) -> QuestionRevision | None:
        statement = select(QuestionRevision).where(QuestionRevision.question_id == q.id)
        if "admin" not in roles:
            statement = statement.where(
                or_(QuestionRevision.created_by == actor, QuestionRevision.status != "draft")
            )
        return cast(
            QuestionRevision | None,
            await db.scalar(statement.order_by(QuestionRevision.revision_number.desc()).limit(1)),
        )

    async def apply_row(
        self, db: AsyncSession, job: ImportJob, row: ImportRow, roles: set[str]
    ) -> None:
        assert row.topic_id is not None and row.content_hash is not None
        topic = await db.get(Topic, row.topic_id)
        discipline = await db.get(Discipline, topic.discipline_id) if topic else None
        category = (
            await db.get(Category, topic.category_id) if topic and topic.category_id else None
        )
        if (
            topic is None
            or discipline is None
            or topic.status == "withdrawn"
            or discipline.status == "withdrawn"
            or (category is not None and category.status == "withdrawn")
        ):
            row.errors = ["TOPIC_NOT_AVAILABLE"]
            row.action = "error"
            return
        body = QuestionBody.model_validate(row.normalized_payload)
        # Source ACL may have changed since staging.
        if body.source_id:
            source = await db.get(ContentSource, body.source_id)
            if (
                source is None
                or source.status == "withdrawn"
                or (
                    "admin" not in roles
                    and source.created_by != job.created_by
                    and source.status != "published"
                )
            ):
                row.errors = ["SOURCE_NOT_AVAILABLE"]
                row.action = "error"
                return
        namespace = "import-topic:" + str(topic.id)
        q = await db.scalar(
            select(Question).where(
                Question.external_source == namespace, Question.external_id == row.external_key
            )
        )
        duplicate = await db.get(ImportContentKey, (topic.id, row.content_hash))
        if duplicate is not None and (q is None or duplicate.question_id != q.id):
            row.action = "duplicate"
            row.warnings = [*row.warnings, "DUPLICATE_CONTENT"]
            candidate = await db.get(Question, duplicate.question_id)
            latest = (
                await self.visible_latest(db, candidate, job.created_by, roles)
                if candidate
                else None
            )
            if latest is not None and latest.fingerprint == row.fingerprint:
                row.target_question_id = latest.question_id
                row.applied_revision_id = latest.id
            return
        if q is not None:
            if q.archived_at is not None:
                row.errors = ["ARCHIVED_QUESTION"]
                row.action = "conflict"
                return
            latest = await self.visible_latest(db, q, job.created_by, roles)
            if latest is None:
                row.errors = ["KEY_NOT_AVAILABLE"]
                row.action = "conflict"
                return
            if latest.fingerprint == row.fingerprint:
                row.action = "unchanged"
                row.target_question_id = q.id
                row.applied_revision_id = latest.id
                return
            if (
                q.current_revision_id is None
                and "admin" not in roles
                and latest.created_by != job.created_by
            ):
                row.errors = ["KEY_NOT_AVAILABLE"]
                row.action = "conflict"
                return
            link = await db.get(TopicQuestion, (topic.id, q.id))
            if link is None and q.current_revision_id is not None:
                row.errors = ["PUBLISHED_LINK_CONFLICT"]
                row.action = "conflict"
                return
            number = (
                await db.scalar(
                    select(func.max(QuestionRevision.revision_number)).where(
                        QuestionRevision.question_id == q.id
                    )
                )
                or 0
            ) + 1
            action = "update"
        else:
            # A same-text candidate is a warning, never a heuristic merge of different questions.
            possible = await db.scalar(
                select(QuestionRevision.id)
                .join(TopicQuestion, TopicQuestion.question_id == QuestionRevision.question_id)
                .where(
                    TopicQuestion.topic_id == topic.id,
                    QuestionRevision.normalized_search_text == normalize(body.text),
                )
                .limit(1)
            )
            if possible is not None:
                row.warnings = [*row.warnings, "POSSIBLE_DUPLICATE"]
            q = Question(id=uuid4(), external_source=namespace, external_id=row.external_key)
            db.add(q)
            await db.flush()
            number = 1
            action = "create"
        revision = QuestionRevision(
            id=uuid4(),
            question_id=q.id,
            revision_number=number,
            kind=body.kind,
            text=body.text,
            explanation=body.explanation,
            source_id=body.source_id,
            source_reference=body.source_reference,
            source_page=body.source_page,
            license_reference=body.license_reference,
            created_by=job.created_by,
            medical_review_by=None,
            reviewed_at=None,
            status="draft",
            fingerprint=fingerprint(body),
        )
        db.add(revision)
        await db.flush()
        db.add_all(
            [
                QuestionOption(
                    id=uuid4(),
                    revision_id=revision.id,
                    position=i,
                    code=o.code,
                    text=o.text,
                    is_correct=o.is_correct,
                )
                for i, o in enumerate(body.options)
            ]
        )
        if await db.get(TopicQuestion, (topic.id, q.id)) is None:
            position = await db.scalar(
                select(func.max(TopicQuestion.position)).where(TopicQuestion.topic_id == topic.id)
            )
            db.add(
                TopicQuestion(
                    topic_id=topic.id,
                    question_id=q.id,
                    position=0 if position is None else position + 1,
                )
            )
        if duplicate is None:
            db.add(
                ImportContentKey(
                    topic_id=topic.id, content_hash=content_hash(body), question_id=q.id
                )
            )
        row.action = action
        row.target_question_id = q.id
        row.applied_revision_id = revision.id
        audit(
            db,
            actor=job.created_by,
            action="import.draft.created",
            entity_type="question_revision",
            entity_id=revision.id,
            request_id=uuid4(),
        )
        # current_revision_id is intentionally never changed by import.
        await db.flush()

    async def apply(self, job_id: UUID, token: UUID) -> None:
        while True:
            async with self.database.sessions.begin() as db:
                owner = await db.scalar(select(ImportJob.created_by).where(ImportJob.id == job_id))
                if owner is None:
                    raise LeaseLost
                roles = await self.actor(db, owner)
                await db.get(CatalogState, 1, with_for_update=True)
                job = await self.fenced(db, job_id, token)
                job.phase = "applying"
                rows = list(
                    (
                        await db.scalars(
                            select(ImportRow)
                            .where(ImportRow.import_job_id == job_id, ImportRow.action == "pending")
                            .order_by(ImportRow.position)
                            .limit(BATCH)
                        )
                    ).all()
                )
                if not rows:
                    break
                for row in rows:
                    await self.apply_row(db, job, row, roles)
                await db.flush()
                await self.summarize(db, job)
                job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            await self.heartbeat(job_id, token)

    async def finalize(
        self, job_id: UUID, token: UUID, status: str, code: str | None = None
    ) -> None:
        async with self.database.sessions.begin() as db:
            job = await db.get(ImportJob, job_id, with_for_update=True)
            if job is None or job.lease_token != token or job.status != "processing":
                return
            job.status = "cancelled" if job.cancel_requested else status
            job.phase = "done"
            job.error_code = code
            job.lease_token = None
            job.lease_until = None
            await self.summarize(db, job)
            audit(
                db,
                actor=job.created_by,
                action="import." + job.status,
                entity_type="import_job",
                entity_id=job.id,
                request_id=uuid4(),
            )

        logger.info(
            "import_job_finished",
            extra={"job_id": str(job.id), "status": job.status, "code": job.error_code},
        )

    async def process(self, job_id: UUID, token: UUID) -> None:
        work = None
        try:
            async with self.database.sessions() as db:
                job = await db.get(ImportJob, job_id)
                assert job is not None
                asset = await db.get(Asset, job.asset_id)
                assert asset is not None
                file_key, fmt, digest = asset.storage_key, job.file_format, job.sha256

            async def check() -> None:
                await self.heartbeat(job_id, token)

            async with asyncio.timeout(600):
                output, metrics, work = await run_parser(self.store, file_key, fmt, digest, check)
                await self.stage(job_id, token, output, int(metrics["count"]))
                await self.apply(job_id, token)
                await self.finalize(job_id, token, "completed")
        except Cancelled:
            await self.finalize(job_id, token, "cancelled")
        except LeaseLost:
            pass
        except ImportFileError as exc:
            await self.finalize(job_id, token, "failed", exc.code)
        except Exception:
            logger.error("import_processing_failed", extra={"job_id": str(job_id)})
            await self.finalize(job_id, token, "failed", "PROCESSING_FAILED")
        finally:
            if work is not None:
                shutil.rmtree(work, ignore_errors=True)

    async def run_once(self) -> bool:
        async with self.database.engine.connect() as connection:
            locked = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}
            )
            await connection.commit()
            if not locked:
                return False
            self.lock_connection = connection
            try:
                claim = await self.claim()
                if claim is None:
                    return False
                await self.process(*claim)
                return True
            finally:
                self.lock_connection = None
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK}
                )
                await connection.commit()


async def run(once: bool) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    worker = Worker(settings)
    try:
        await worker.database.check_ready()
        while True:
            handled = await worker.run_once()
            if once:
                break
            if not handled:
                await asyncio.sleep(2)
    finally:
        await worker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Private MEDEXA draft import worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("IMPORT_WORKER_FAILED: check configuration and readiness") from None


if __name__ == "__main__":
    main()
