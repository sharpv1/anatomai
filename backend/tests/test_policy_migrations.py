import asyncio

import pytest
from alembic import command
from sqlalchemy import text

from app.db.database import Database

pytestmark = pytest.mark.integration


def test_policy_migration_preserves_rows_and_invalidates_catalog_cursors(
    migrated_database, alembic_config, db_settings
):
    async def snapshot():
        db = Database(db_settings)
        try:
            async with db.sessions() as session:
                version = await session.scalar(text("SELECT version FROM catalog_state WHERE id=1"))
                rows = {
                    table: sorted(
                        (
                            await session.scalars(text(f"SELECT to_jsonb(t)::text FROM {table} t"))
                        ).all()
                    )
                    for table in (
                        "questions",
                        "question_revisions",
                        "question_options",
                        "content_sources",
                    )
                }
                return version, rows
        finally:
            await db.dispose()

    before_version, before_rows = asyncio.run(snapshot())
    command.downgrade(alembic_config, "0004_admin")
    down_version, down_rows = asyncio.run(snapshot())
    assert down_version > before_version and down_rows == before_rows
    command.upgrade(alembic_config, "head")
    up_version, up_rows = asyncio.run(snapshot())
    assert up_version > down_version and up_rows == before_rows
    command.check(alembic_config)
