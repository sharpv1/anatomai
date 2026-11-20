import asyncio

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from app.db.database import Database
from app.db.schema import EXPECTED_SCHEMA_REVISION

pytestmark = pytest.mark.integration


def test_migration_roundtrip_single_head_and_no_schema_drift(
    migrated_database, alembic_config, db_settings
):
    assert ScriptDirectory.from_config(alembic_config).get_heads() == [EXPECTED_SCHEMA_REVISION]
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)

    async def readiness():
        database = Database(db_settings)
        try:
            await database.check_ready()
        finally:
            await database.dispose()

    asyncio.run(readiness())
