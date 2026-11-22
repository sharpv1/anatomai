import asyncio

import pytest
from alembic import command
from sqlalchemy import text

from app.db.database import Database

pytestmark = pytest.mark.integration


def test_admin_downgrade_preserves_content_and_identity(
    migrated_database, alembic_config, db_settings
):
    async def snapshot():
        database = Database(db_settings)
        try:
            async with database.sessions() as db:
                return {
                    table: sorted(
                        (
                            await db.scalars(
                                text(
                                    f"SELECT (to_jsonb(t) - 'created_by')::text FROM {table} t"
                                    if table == "content_sources"
                                    else (
                                        "SELECT (to_jsonb(t) - 'license_reference')::text "
                                        f"FROM {table} t"
                                    )
                                    if table == "question_revisions"
                                    else f"SELECT to_jsonb(t)::text FROM {table} t"
                                )
                            )
                        ).all()
                    )
                    for table in (
                        "users",
                        "user_sessions",
                        "questions",
                        "question_revisions",
                        "question_options",
                        "content_sources",
                    )
                }
        finally:
            await database.dispose()

    before = asyncio.run(snapshot())
    command.downgrade(alembic_config, "0003_content")
    assert asyncio.run(snapshot()) == before
    command.upgrade(alembic_config, "0004_admin")
    assert asyncio.run(snapshot()) == before
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
