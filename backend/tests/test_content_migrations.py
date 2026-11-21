import asyncio

import pytest
from alembic import command
from sqlalchemy import text

from app.db.database import Database

pytestmark = pytest.mark.integration


def test_content_roundtrip_preserves_identity(migrated_database, alembic_config, db_settings):
    async def identity_snapshot():
        database = Database(db_settings)
        try:
            async with database.sessions() as db:
                return {
                    table: (await db.execute(text(f"SELECT row_to_json(t)::text FROM {table} t")))
                    .scalars()
                    .all()
                    for table in ("users", "roles", "user_roles", "user_sessions", "auth_replays")
                }
        finally:
            await database.dispose()

    before = asyncio.run(identity_snapshot())
    command.downgrade(alembic_config, "0002_identity")
    assert asyncio.run(identity_snapshot()) == before
    command.upgrade(alembic_config, "0003_content")
    assert asyncio.run(identity_snapshot()) == before
    command.check(alembic_config)
