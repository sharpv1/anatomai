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

from app.admin import models as admin_models  # noqa: F401 -- metadata
from app.attempts import models as attempt_models  # noqa: F401 -- metadata
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
from app.db import models as foundation_models  # noqa: F401 -- metadata
from app.db.base import Base
from app.db.database import Database
from app.identity.models import User, UserRole
from app.imports import models as import_models  # noqa: F401 -- metadata
from app.publishing import models as publishing_models  # noqa: F401 -- metadata

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


@pytest.fixture
async def admin_clients(database, db_settings, monkeypatch):
    from contextlib import asynccontextmanager
    from datetime import timedelta
    from unittest.mock import patch

    from admin_helpers import MFA_KEY, TOTP_SECRET, AdminActor
    from httpx import ASGITransport, AsyncClient
    from identity_helpers import ORIGIN, TEST_BOT_TOKEN, TEST_CSRF_KEY, signed_data
    from pydantic import SecretStr

    from app.admin.mfa import MFA_ROLES, provision, totp
    from app.main import create_app

    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    clock = [datetime.now(UTC)]
    monkeypatch.setattr("app.admin.mfa.utcnow", lambda: clock[0])
    settings = db_settings.model_copy(
        update={
            "telegram_bot_token": SecretStr(TEST_BOT_TOKEN),
            "csrf_signing_key": SecretStr(TEST_CSRF_KEY),
            "content_cursor_signing_key": SecretStr("synthetic-cursor-key-" + "s" * 40),
            "mfa_encryption_key": SecretStr(MFA_KEY),
            "app_origin": ORIGIN,
            "login_rate_limit": 100,
        }
    )

    @asynccontextmanager
    async def make(role="content_editor", *, confirmed=True, enrolled=True):
        user_id, telegram_id = uuid4(), uuid4().int % (2**62) + 1
        async with database.sessions.begin() as db:
            db.add(User(id=user_id, telegram_user_id=telegram_id))
            await db.flush()
            db.add(UserRole(user_id=user_id, role_code=role))
        try:
            codes = []
            if enrolled and role in MFA_ROLES:
                previous = clock[0] - timedelta(seconds=60)
                with patch("app.admin.mfa.utcnow", lambda: previous):
                    async with database.sessions.begin() as db:
                        codes = await provision(
                            db,
                            settings,
                            telegram_id,
                            TOTP_SECRET,
                            totp(TOTP_SECRET, int(previous.timestamp()) // 30),
                        )
            app = create_app(settings)
            async with app.router.lifespan_context(app):
                async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
                    response = await client.post(
                        "/api/v1/auth/telegram",
                        json={"init_data": signed_data(telegram_id)},
                        headers={"Origin": ORIGIN},
                    )
                    assert response.status_code == 200, response.text
                    headers = {
                        "Origin": ORIGIN,
                        "X-CSRF-Token": response.json()["data"]["csrf_token"],
                    }
                    actor = AdminActor(
                        client, user_id, telegram_id, headers, app, settings, clock, codes
                    )
                    if confirmed:
                        response = await client.post(
                            "/api/v1/admin/auth/step-up",
                            json={"code": actor.code()},
                            headers=headers,
                        )
                        assert response.status_code == 200, response.text
                        actor.grant = response.json()["data"]
                    yield actor
        finally:
            from sqlalchemy import delete

            # Fixture roles must not leak into the existing singleton-admin bootstrap tests.
            # Keep users/revisions/audit history intact, just retire this actor's test roles.
            async with database.sessions.begin() as db:
                await db.execute(delete(UserRole).where(UserRole.user_id == user_id))

    return make
