import asyncio
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.content import models as content_models  # noqa: F401 -- metadata
from app.content.models import (
    Category,
    ContentSource,
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.content.models import (
    TestDefinition as Definition,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.database import Database
from app.identity.models import User, UserRole

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


@pytest.fixture
async def content_data(database, make_actor):
    author, reviewer = await make_actor(), await make_actor()
    suffix = uuid4().hex
    async with database.sessions.begin() as db:
        db.add(UserRole(user_id=reviewer, role_code="content_reviewer"))
        await db.flush()
        source = ContentSource(
            id=uuid4(),
            slug="test-" + suffix,
            title="SYNTHETIC TEST SOURCE",
            attribution="TEST ONLY, not a medical source",
            license_reference="SYNTHETIC FIXTURE ONLY",
            reviewed_by=reviewer,
            reviewed_at=datetime.now(UTC),
            status="published",
        )
        d = Discipline(
            id=uuid4(),
            slug=suffix,
            title="Служебная дисциплина " + suffix,
            icon_key="test",
            color_token="blue",
            position=0,
            status="published",
        )
        db.add_all([source, d])
        await db.flush()
        category = Category(
            id=uuid4(),
            discipline_id=d.id,
            slug=suffix,
            title="Служебная категория",
            position=0,
            status="published",
        )
        db.add(category)
        await db.flush()
        topic = Topic(
            id=uuid4(),
            discipline_id=d.id,
            category_id=category.id,
            slug=suffix,
            title="Служебная тема " + suffix,
            position=0,
            status="published",
        )
        db.add(topic)
        await db.flush()
        definition = Definition(
            id=uuid4(),
            topic_id=topic.id,
            slug=suffix,
            title="Служебный набор",
            exam_duration_seconds=90,
            status="published",
            internal_difficulty="DO-NOT-EXPOSE",
        )
        db.add(definition)
        questions = []
        revisions = []
        options = []
        for i in range(3):
            q = Question(id=uuid4(), external_source="synthetic-tests", external_id=uuid4().hex)
            db.add(q)
            await db.flush()
            revision = QuestionRevision(
                id=uuid4(),
                question_id=q.id,
                revision_number=1,
                text=[
                    "Служебный Ёж врач 100%_",
                    "Служебный длинный вопрос " + "текст " * 100,
                    "DRAFT SECRET QUESTION",
                ][i],
                explanation="SECRET-EXPLANATION",
                source_id=source.id,
                created_by=author,
                medical_review_by=reviewer,
                reviewed_at=datetime.now(UTC),
                fingerprint=hashlib.sha256((suffix + str(i)).encode()).hexdigest(),
                status="draft",
            )
            db.add(revision)
            await db.flush()
            choices = [
                QuestionOption(
                    id=uuid4(),
                    revision_id=revision.id,
                    position=j,
                    code=chr(65 + j),
                    text="Служебный вариант " + str(j),
                    is_correct=j == 0,
                )
                for j in range(2)
            ]
            db.add_all(choices)
            await db.flush()
            if i < 2:
                revision.status = "published"
                await db.flush()
                q.current_revision_id = revision.id
            db.add(TopicQuestion(topic_id=topic.id, question_id=q.id, position=i))
            questions.append(q)
            revisions.append(revision)
            options.append(choices)
        return dict(
            d=d,
            category=category,
            topic=topic,
            definition=definition,
            source=source,
            author=author,
            reviewer=reviewer,
            questions=questions,
            revisions=revisions,
            options=options,
            suffix=suffix,
        )
