"""Explicit operator maintenance; never scheduled by the HTTP process."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.database import Database
from app.identity.models import AuditEvent, AuthReplay, UserSession


async def cleanup_expired(db: AsyncSession) -> tuple[int, int]:
    now = datetime.now(UTC)
    expired_replays = (
        select(AuthReplay.init_data_digest)
        .where(AuthReplay.valid_until < now - timedelta(days=1))
        .order_by(AuthReplay.valid_until)
        .limit(500)
        .with_for_update(skip_locked=True)
    )
    replays = (
        (
            await db.execute(
                delete(AuthReplay)
                .where(AuthReplay.init_data_digest.in_(expired_replays))
                .returning(AuthReplay.init_data_digest)
            )
        )
        .scalars()
        .all()
    )
    referenced = exists(
        select(AuthReplay.init_data_digest).where(AuthReplay.session_id == UserSession.id)
    )
    old_sessions = (
        select(UserSession.id)
        .where(
            or_(
                UserSession.expires_at < now - timedelta(days=30),
                UserSession.revoked_at < now - timedelta(days=30),
            ),
            ~referenced,
        )
        .order_by(UserSession.expires_at)
        .limit(500)
        .with_for_update(skip_locked=True)
    )
    sessions = (
        (
            await db.execute(
                delete(UserSession)
                .where(UserSession.id.in_(old_sessions))
                .returning(UserSession.id)
            )
        )
        .scalars()
        .all()
    )
    if replays or sessions:
        db.add(
            AuditEvent(
                actor_id=None,
                action="auth.maintenance",
                entity_type="system",
                entity_id=uuid4(),
                request_id=uuid4(),
                safe_diff={"replays_removed": len(replays), "sessions_removed": len(sessions)},
            )
        )
    return len(replays), len(sessions)


async def run() -> None:
    database = Database(Settings())
    try:
        await database.check_ready()
        async with database.sessions.begin() as db:
            replays, sessions = await cleanup_expired(db)
        print(
            f"Expired replay records removed: {replays}; old inactive sessions removed: {sessions}"
        )
    except Exception:
        raise SystemExit("MAINTENANCE_FAILED: check configuration and database readiness") from None
    finally:
        await database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean expired auth records; preserve users and audit"
    )
    parser.add_argument("--confirm", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(run())
