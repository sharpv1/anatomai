"""Explicitly confirmed commands only; shares import singleton lock and runtime limits."""

import argparse
import asyncio
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.models import CatalogState
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import configure_logging
from app.identity.models import User, UserRole
from app.identity.service import audit
from app.imports.limits import BATCH, LEASE_SECONDS, MAX_ATTEMPTS
from app.imports.models import ImportJob
from app.imports.worker import Cancelled, LeaseLost, Worker, now
from app.publishing.models import PublicationItem, PublicationRun
from app.publishing.service import publish_one
from app.publishing.snapshots import digest, fail, snapshots, staging, verify_file

logger = logging.getLogger(__name__)


class PublishingWorker(Worker):
    # Parent run_once provides exactly the same singleton advisory-lock/fencing connection.
    async def claim(self) -> tuple[UUID, UUID] | None:
        async with self.database.sessions.begin() as db:
            run = await db.scalar(
                select(PublicationRun)
                .where(
                    or_(
                        PublicationRun.status == "queued",
                        and_(
                            PublicationRun.status == "processing",
                            PublicationRun.lease_until < now(),
                        ),
                    )
                )
                .order_by(PublicationRun.sequence)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if run is None:
                return None
            if run.cancel_requested or run.attempts >= MAX_ATTEMPTS:
                run.status = "cancelled" if run.cancel_requested else "failed"
                run.error_code = None if run.cancel_requested else "LEASE_EXHAUSTED"
                run.lease_until = None
                run.lease_token = None
                run.updated_at = now()
                return None
            run.status = "processing"
            run.attempts += 1
            run.error_code = None
            run.lease_token = uuid4()
            run.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            run.updated_at = now()
            return run.id, run.lease_token

    async def publication_fenced(
        self, db: AsyncSession, run_id: UUID, token: UUID
    ) -> PublicationRun:
        run = await db.get(PublicationRun, run_id, with_for_update=True)
        if (
            run is None
            or run.status != "processing"
            or run.lease_token != token
            or run.lease_until is None
            or run.lease_until <= now()
        ):
            raise LeaseLost
        if run.cancel_requested:
            raise Cancelled
        return run

    async def heartbeat(self, run_id: UUID, token: UUID) -> None:
        if self.lock_connection is not None:
            await self.lock_connection.execute(text("SELECT 1"))
            await self.lock_connection.commit()
        async with self.database.sessions.begin() as db:
            run = await self.publication_fenced(db, run_id, token)
            run.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            run.updated_at = now()

    async def admin_actor(self, db: AsyncSession, actor: UUID) -> None:
        user = await db.get(User, actor, with_for_update=True)
        role = await db.scalar(
            select(UserRole.role_code).where(
                UserRole.user_id == actor, UserRole.role_code == "admin"
            )
        )
        if user is None or user.status != "active" or role is None:
            raise fail("ACCESS_REVOKED")

    async def batch(self, run_id: UUID, token: UUID) -> bool:
        async with self.database.sessions.begin() as db:
            actor = await db.scalar(
                select(PublicationRun.confirmed_by).where(PublicationRun.id == run_id)
            )
            if actor is None:
                raise LeaseLost
            await self.admin_actor(db, actor)
            await db.get(CatalogState, 1, with_for_update=True)
            run = await self.publication_fenced(db, run_id, token)
            job = await db.get(ImportJob, run.import_job_id, with_for_update=True)
            assert job
            await verify_file(db, self.settings, job)
            stage_hash, _ = await staging(db, job)
            if (
                stage_hash != run.staging_hash
                or job.sha256 != run.file_sha256
                or job.template_version != run.template_version
                or job.result_version != run.result_version
            ):
                raise fail("STAGING_CHANGED")
            positions = list(
                (
                    await db.scalars(
                        select(PublicationItem.position)
                        .where(PublicationItem.run_id == run_id)
                        .order_by(PublicationItem.position)
                    )
                ).all()
            )
            if len(positions) != run.selected_count or digest(positions) != run.selection_hash:
                raise fail("SELECTION_CHANGED")
            items = list(
                (
                    await db.scalars(
                        select(PublicationItem)
                        .where(
                            PublicationItem.run_id == run_id, PublicationItem.status == "pending"
                        )
                        .order_by(PublicationItem.position)
                        .limit(BATCH)
                    )
                ).all()
            )
            if not items:
                return False
            current = await snapshots(db, [item.revision_id for item in items])
            # Validate entire batch before any status/pointer writes.
            for item in items:
                if current.get(item.revision_id) != item.snapshot:
                    raise ApplicationError(
                        "STALE_ITEM",
                        "Выбранная редакция изменилась. Нужен новый предпросмотр.",
                        409,
                        {"position": item.position},
                    )
            for item in items:
                item.status = await publish_one(db, item.revision_id, actor, run_id)
            run.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            run.updated_at = now()
            await db.flush()
            # Force deferred structural/pointer guards inside this batch, not a later transaction.
            await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            return True

    async def finish(
        self,
        run_id: UUID,
        token: UUID,
        status: str,
        code: str | None = None,
        position: int | None = None,
    ) -> None:
        async with self.database.sessions.begin() as db:
            run = await db.get(PublicationRun, run_id, with_for_update=True)
            if run is None or run.status != "processing" or run.lease_token != token:
                return
            run.status = "cancelled" if run.cancel_requested else status
            run.error_code = code
            run.lease_token = None
            run.lease_until = None
            run.updated_at = now()
            if position is not None:
                item = await db.scalar(
                    select(PublicationItem).where(
                        PublicationItem.run_id == run_id,
                        PublicationItem.position == position,
                        PublicationItem.status == "pending",
                    )
                )
                if item:
                    item.status = "failed"
                    item.error_code = code
            audit(
                db,
                actor=run.confirmed_by,
                action="publication." + run.status,
                entity_type="publication_run",
                entity_id=run.id,
                request_id=run.id,
            )
        logger.info(
            "publication_finished", extra={"job_id": str(run_id), "status": status, "code": code}
        )

    async def process(self, run_id: UUID, token: UUID) -> None:
        try:
            async with asyncio.timeout(600):
                while await self.batch(run_id, token):
                    await self.heartbeat(run_id, token)
                await self.finish(run_id, token, "completed")
        except Cancelled:
            await self.finish(run_id, token, "cancelled")
        except LeaseLost:
            pass
        except ApplicationError as exc:
            position = exc.details.get("position")
            await self.finish(
                run_id,
                token,
                "failed",
                exc.code,
                int(position) if isinstance(position, int) else None,
            )
        except Exception:
            logger.error("publication_failed", extra={"job_id": str(run_id)})
            await self.finish(run_id, token, "failed", "PROCESSING_FAILED")


async def run(once: bool, with_imports: bool = False) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    worker = PublishingWorker(settings)
    importer = Worker(settings, database=worker.database) if with_imports else None
    try:
        await worker.database.check_ready()
        while True:
            handled = await worker.run_once()
            if importer is not None and (not once or not handled):
                imported = await importer.run_once()
                handled = handled or imported
            if once:
                break
            if not handled:
                await asyncio.sleep(2)
    finally:
        await worker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit MEDEXA publication worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--with-imports", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once, args.with_imports))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("PUBLICATION_WORKER_FAILED: check configuration and readiness") from None


if __name__ == "__main__":
    main()
