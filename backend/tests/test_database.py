from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.database import Database, SchemaNotReady, UnsupportedPostgresVersion
from app.db.schema import EXPECTED_SCHEMA_REVISION


@pytest.mark.parametrize(
    "version,revisions,error",
    [
        ("160004", [EXPECTED_SCHEMA_REVISION], None),
        ("170000", [EXPECTED_SCHEMA_REVISION], UnsupportedPostgresVersion),
        ("150009", [EXPECTED_SCHEMA_REVISION], UnsupportedPostgresVersion),
        ("160004", [], SchemaNotReady),
        ("160004", ["older"], SchemaNotReady),
        ("160004", [EXPECTED_SCHEMA_REVISION, "another_head"], SchemaNotReady),
    ],
)
async def test_readiness_requires_pg16_and_exact_schema(settings, version, revisions, error):
    database = Database(settings)
    connection = AsyncMock()
    connection.scalar.return_value = version
    result = MagicMock()
    result.scalars.return_value.all.return_value = revisions
    connection.execute.return_value = result
    fake_engine = MagicMock()
    fake_engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    real_engine = database.engine
    database.engine = fake_engine
    try:
        if error:
            with pytest.raises(error):
                await database.check_ready()
        else:
            await database.check_ready()
            assert connection.execute.await_count == 2
    finally:
        await real_engine.dispose()
