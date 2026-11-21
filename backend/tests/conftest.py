import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.base import Base
from app.db.database import Database
from app.identity.models import User

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings():
    return Settings(
        environment="test",
        db_host="127.0.0.1",
        db_port=1,
        db_name="medexa_foundation_unit",
        db_user="unused",
        db_password="unit-only-not-a-real-credential",
    )


@pytest.fixture(scope="session")
def db_settings():
    if os.environ.get("MEDEXA_RUN_DB_TESTS") != "1":
        pytest.skip("Set MEDEXA_RUN_DB_TESTS=1 with the isolated PostgreSQL 16 test database")
    settings = Settings()
    if settings.environment != "test" or settings.db_name != "medexa_foundation_test":
        pytest.fail("Refusing destructive tests outside medexa_foundation_test / environment=test")
    return settings


@pytest.fixture(scope="session")
def alembic_config(db_settings):
    return Config(str(ROOT / "alembic.ini"))


@pytest.fixture(scope="session")
def migrated_database(alembic_config, db_settings):
    async def verify_target():
        engine = create_async_engine(db_settings.database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                version = int(await connection.scalar(text("SHOW server_version_num")))
                assert 160000 <= version < 170000, "PostgreSQL 16 is required"
                unexpected = await connection.scalars(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND NOT(tablename = ANY(:allowed))"
                    ),
                    {"allowed": ["alembic_version", *Base.metadata.tables]},
                )
                assert not unexpected.all(), "Refusing to modify a database with unrelated tables"
        finally:
            await engine.dispose()

    asyncio.run(verify_target())
    command.upgrade(alembic_config, "head")


@pytest.fixture
async def database(migrated_database, db_settings):
    database = Database(db_settings)
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
async def make_actor(database):
    async def make():
        user = User(id=uuid4(), telegram_user_id=uuid4().int % (2**62) + 1)
        async with database.sessions.begin() as db:
            db.add(user)
        return user.id

    return make


@pytest.fixture
async def actor(make_actor):
    return await make_actor()
