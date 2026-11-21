"""Explicit local retention command; no deletion of drafts, reports or audit history."""

import asyncio
import re
import shutil
from datetime import timedelta

from sqlalchemy import select, text

from app.content.models import Asset
from app.core.config import Settings
from app.imports.models import ImportJob
from app.imports.worker import WORKER_LOCK, Worker, now


async def cleanup(worker: Worker) -> int:
    # Shares the worker singleton lock: never remove an active parser work directory.
    removed = 0
    async with worker.database.engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}
        )
        await connection.commit()
        if not acquired:
            return 0
        try:
            paths = []
            async with worker.database.sessions.begin() as db:
                jobs = list(
                    (
                        await db.scalars(
                            select(ImportJob)
                            .where(
                                ImportJob.status.in_(["completed", "failed", "cancelled"]),
                                ImportJob.raw_deleted_at.is_(None),
                                ImportJob.updated_at < now() - timedelta(days=30),
                            )
                            .limit(100)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
                for job in jobs:
                    asset = await db.get(Asset, job.asset_id)
                    assert asset is not None
                    paths.append(worker.store.path(asset.storage_key))
                    job.raw_deleted_at = now()
            # DB marks retention first. A crash leaves an orphan, never a retryable missing file.
            for path in paths:
                path.unlink(missing_ok=True)
                removed += 1
            examined = 0
            for path in worker.store.root.iterdir():
                examined += 1
                if examined > 10000:
                    break
                if (
                    path.is_symlink()
                    or path.stat().st_mtime > (now() - timedelta(days=1)).timestamp()
                ):
                    continue
                if re.fullmatch(r"work-[0-9a-f]{32}", path.name) and path.is_dir():
                    shutil.rmtree(path)
                    removed += 1
                elif re.fullmatch(r"[0-9a-f]{32}", path.name) and path.is_file():
                    async with worker.database.sessions() as db:
                        retained = await db.scalar(
                            select(ImportJob.id)
                            .join(Asset, ImportJob.asset_id == Asset.id)
                            .where(
                                Asset.storage_key == path.name, ImportJob.raw_deleted_at.is_(None)
                            )
                        )
                    if retained is None:
                        path.unlink()
                        removed += 1
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK})
            await connection.commit()
    return removed


async def run() -> None:
    worker = Worker(Settings())
    try:
        await worker.database.check_ready()
        print("removed:", await cleanup(worker))
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(run())
