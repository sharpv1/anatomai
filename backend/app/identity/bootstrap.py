"""Operator-only first-admin bootstrap. Never imported as an HTTP handler."""

import argparse
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.database import Database
from app.identity.models import User, UserRole, UserSession
from app.identity.service import audit


async def bootstrap_admin(db: AsyncSession, telegram_user_id: int) -> bool:
    await db.execute(text("SELECT pg_advisory_xact_lock(72634012002)"))
    user = await db.scalar(
        select(User).where(User.telegram_user_id == telegram_user_id).with_for_update()
    )
    if user is None or user.status != "active":
        raise ApplicationError(
            "BOOTSTRAP_USER_REQUIRED",
            "Нужен существующий активный пользователь, вошедший через Telegram.",
        )
    admins = set(
        (await db.scalars(select(UserRole.user_id).where(UserRole.role_code == "admin"))).all()
    )
    if admins == {user.id}:
        return False
    if admins:
        raise ApplicationError("BOOTSTRAP_CLOSED", "Первый администратор уже назначен.")
    db.add(UserRole(user_id=user.id, role_code="admin", granted_by=None))
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    audit(
        db,
        actor=None,
        action="admin.bootstrapped",
        entity_type="user",
        entity_id=user.id,
        request_id=uuid4(),
    )
    return True


async def run(telegram_user_id: int) -> None:
    database = Database(Settings())
    try:
        await database.check_ready()
        async with database.sessions.begin() as db:
            changed = await bootstrap_admin(db, telegram_user_id)
        print(
            "Administrator bootstrapped; previous sessions revoked."
            if changed
            else "Bootstrap already completed for this user."
        )
    except ApplicationError as exc:
        raise SystemExit(exc.code) from None
    except Exception:
        # No raw driver/config exception or DSN in the operator output.
        raise SystemExit("BOOTSTRAP_FAILED: check configuration and database readiness") from None
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign the first admin to a verified existing user"
    )
    parser.add_argument("--telegram-user-id", type=int, required=True)
    parser.add_argument("--confirm", action="store_true", required=True)
    args = parser.parse_args()
    if not 0 < args.telegram_user_id <= 2**63 - 1:
        parser.error("Invalid Telegram ID")
    asyncio.run(run(args.telegram_user_id))


if __name__ == "__main__":
    main()
