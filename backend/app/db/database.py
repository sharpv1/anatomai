from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.schema import EXPECTED_SCHEMA_REVISION


class SchemaNotReady(Exception):
    pass


class UnsupportedPostgresVersion(Exception):
    pass


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=0,
            pool_timeout=1,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "timeout": 2,
                "command_timeout": 2,
                "server_settings": {
                    "application_name": "medexa_foundation",
                    "statement_timeout": "2000",
                    "lock_timeout": "1000",
                },
            },
        )
        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def check_ready(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            version = await connection.scalar(text("SELECT current_setting('server_version_num')"))
            if not 160000 <= int(version) < 170000:
                raise UnsupportedPostgresVersion
            revisions = await connection.execute(text("SELECT version_num FROM alembic_version"))
            if revisions.scalars().all() != [EXPECTED_SCHEMA_REVISION]:
                raise SchemaNotReady

    async def dispose(self) -> None:
        await self.engine.dispose()
