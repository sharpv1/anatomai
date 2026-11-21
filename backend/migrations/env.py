import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin import models as admin_models  # noqa: F401 -- metadata
from app.content import models as content_models  # noqa: F401 -- metadata
from app.core.config import Settings
from app.db.base import Base
from app.db.models import IdempotencyRequest  # noqa: F401 -- register metadata
from app.identity import models  # noqa: F401 -- register identity metadata
from app.imports import models as import_models  # noqa: F401 -- metadata
from app.publishing import models as publishing_models  # noqa: F401 -- metadata

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SELECT pg_advisory_xact_lock(72634012001)"))
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # No interpolation of credentials into alembic.ini and no shared API pool.
    engine = create_async_engine(
        Settings().database_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 30},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
