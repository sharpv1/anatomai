"""Small DB-backed deadline worker. No Redis or in-memory job queue."""

import argparse
import asyncio
import logging

from sqlalchemy import func, select

from app.attempts.exam import expire
from app.attempts.models import Attempt
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.database import Database
from app.identity.models import User

logger = logging.getLogger(__name__)


async def run_once(database: Database) -> bool:
    # Same lock order as HTTP identity: user -> attempt, one short transaction.
    async with database.sessions.begin() as db:
        user = await db.scalar(
            select(User)
            .join(Attempt, Attempt.user_id == User.id)
            .where(
                Attempt.mode == "exam",
                Attempt.status == "in_progress",
                Attempt.deadline_at <= func.clock_timestamp(),
            )
            .order_by(Attempt.deadline_at)
            .limit(1)
            .with_for_update(of=User, skip_locked=True)
        )
        if user is None:
            return False
        a = await db.scalar(
            select(Attempt)
            .where(
                Attempt.user_id == user.id, Attempt.mode == "exam", Attempt.status == "in_progress"
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await expire(db, a) if a is not None else False


async def run(once: bool) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    try:
        await database.check_ready()
        while True:
            try:
                handled = await run_once(database)
            except Exception:
                if once:
                    raise
                logger.error("exam_finalizer_iteration_failed")
                handled = False
            if once:
                return
            if not handled:
                await asyncio.sleep(2)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="MEDEXA exam deadline finalizer")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("EXAM_FINALIZER_FAILED: check configuration and readiness") from None


if __name__ == "__main__":
    main()
