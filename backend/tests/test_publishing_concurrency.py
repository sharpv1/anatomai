"""Real concurrent HTTP/worker commits in a disposable PostgreSQL database."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from admin_helpers import MFA_KEY, TOTP_SECRET
from alembic import command
from httpx import ASGITransport, AsyncClient
from identity_helpers import ORIGIN, TEST_BOT_TOKEN, TEST_CSRF_KEY, signed_data
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.mfa import provision, totp
from app.content.models import Discipline, Topic
from app.db.database import Database
from app.identity.models import AuditEvent, User, UserRole
from app.imports.templates import document
from app.imports.worker import Worker
from app.main import create_app
from app.publishing.models import PublicationCommand
from app.publishing.worker import PublishingWorker

pytestmark = pytest.mark.integration


@pytest.fixture
def committed_settings(migrated_database, db_settings, alembic_config, monkeypatch, tmp_path):
    name = "medexa_foundation_race_" + uuid4().hex[:12]

    async def ddl(create):
        engine = create_async_engine(db_settings.database_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                # Name is wholly generated, never supplied by a user or an environment variable.
                if create:
                    await conn.execute(text(f'CREATE DATABASE "{name}"'))
                else:
                    await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        finally:
            await engine.dispose()

    asyncio.run(ddl(True))
    try:
        monkeypatch.setenv("MEDEXA_DB_NAME", name)
        command.upgrade(alembic_config, "head")
        yield db_settings.model_copy(
            update={
                "db_name": name,
                "telegram_bot_token": SecretStr(TEST_BOT_TOKEN),
                "csrf_signing_key": SecretStr(TEST_CSRF_KEY),
                "content_cursor_signing_key": SecretStr("synthetic-race-cursor-" + "s" * 40),
                "mfa_encryption_key": SecretStr(MFA_KEY),
                "app_origin": ORIGIN,
                "import_storage_dir": tmp_path / "private",
            }
        )
    finally:
        asyncio.run(ddl(False))


@asynccontextmanager
async def authenticated(settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    db = Database(settings)
    uid = uuid4()
    tid = uuid4().int % (2**62) + 1
    async with db.sessions.begin() as session:
        session.add(User(id=uid, telegram_user_id=tid))
        await session.flush()
        session.add(UserRole(user_id=uid, role_code="admin"))
    previous = datetime.now(UTC) - timedelta(seconds=60)
    from unittest.mock import patch

    with patch("app.admin.mfa.utcnow", lambda: previous):
        async with db.sessions.begin() as session:
            await provision(
                session,
                settings,
                tid,
                TOTP_SECRET,
                totp(TOTP_SECRET, int(previous.timestamp()) // 30),
            )
    app = create_app(settings)
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
                login = await client.post(
                    "/api/v1/auth/telegram",
                    json={"init_data": signed_data(tid)},
                    headers={"Origin": ORIGIN},
                )
                assert login.status_code == 200, login.text
                headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["data"]["csrf_token"]}
                mfa = await client.post(
                    "/api/v1/admin/auth/step-up",
                    json={"code": totp(TOTP_SECRET, int(datetime.now(UTC).timestamp()) // 30)},
                    headers=headers,
                )
                assert mfa.status_code == 200, mfa.text
                yield client, headers, db
    finally:
        await db.dispose()


async def test_real_concurrent_confirmations_and_workers_are_idempotent(
    committed_settings, monkeypatch
):
    settings = committed_settings
    async with authenticated(settings, monkeypatch) as (client, headers, db):
        async with db.sessions.begin() as session:
            d = Discipline(
                id=uuid4(),
                slug=uuid4().hex,
                title="SYNTHETIC RACE",
                icon_key="test",
                color_token="blue",
                status="published",
            )
            session.add(d)
            await session.flush()
            topic = Topic(
                id=uuid4(),
                discipline_id=d.id,
                slug=uuid4().hex,
                title="SYNTHETIC RACE TOPIC",
                status="published",
            )
            session.add(topic)
        upload = await client.post(
            "/api/v1/admin/imports?format=xlsx",
            content=document(
                "xlsx",
                [
                    [d.slug, topic.slug, "SYNTHETIC RACE QUESTION", "A", "B", "A"],
                    [d.slug, topic.slug, "SECOND RACE QUESTION", "A", "B", "A"],
                ],
            ),
            headers={**headers, "Content-Type": "application/octet-stream"},
        )
        assert upload.status_code == 201, upload.text
        jid = upload.json()["data"]["id"]
        importer = Worker(settings)
        first = PublishingWorker(settings)
        second = PublishingWorker(settings)
        try:
            assert await importer.run_once()
            preview = await client.get(f"/api/v1/admin/imports/{jid}/publication-preview")
            assert preview.status_code == 200, preview.text
            p = preview.json()["data"]
            body = {
                "confirm": True,
                "preview_hash": p["preview_hash"],
                "file_sha256": p["file_sha256"],
                "template_version": 1,
                "selected_positions": [1],
            }
            confirmed_headers = {
                **headers,
                "If-Match": preview.headers["etag"],
                "Idempotency-Key": str(uuid4()),
            }
            responses = await asyncio.gather(
                *(
                    client.post(
                        f"/api/v1/admin/imports/{jid}/publish", json=body, headers=confirmed_headers
                    )
                    for _ in range(2)
                )
            )
            assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
            assert responses[0].json()["data"] == responses[1].json()["data"]
            pid = responses[0].json()["data"]["publication_id"]
            workers = await asyncio.gather(first.run_once(), second.run_once())
            assert sorted(workers) == [False, True]
            result = (await client.get(f"/api/v1/admin/publications/{pid}")).json()["data"]
            assert result["counts"]["published"] == 1
            # Distinct keys racing on one draft cannot both mutate the catalog.
            from app.imports.models import ImportRow

            async with db.sessions() as session:
                rid = await session.scalar(
                    select(ImportRow.applied_revision_id).where(
                        ImportRow.import_job_id == UUID(jid), ImportRow.position == 2
                    )
                )
            rp = await client.get(f"/api/v1/admin/question-revisions/{rid}/publication-preview")
            rb = {"confirm": True, "preview_hash": rp.json()["data"]["preview_hash"]}
            responses = await asyncio.gather(
                *(
                    client.post(
                        f"/api/v1/admin/question-revisions/{rid}/publish",
                        json=rb,
                        headers={
                            **headers,
                            "If-Match": rp.headers["etag"],
                            "Idempotency-Key": str(uuid4()),
                        },
                    )
                    for _ in range(2)
                )
            )
            assert sorted(r.status_code for r in responses) == [200, 412], [
                r.text for r in responses
            ]
            async with db.sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(PublicationCommand)) == 2
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(AuditEvent.action == "question.published")
                    )
                    == 2
                )
        finally:
            await importer.close()
            await first.close()
            await second.close()


async def test_two_admins_cannot_confirm_same_import_concurrently(committed_settings, monkeypatch):
    settings = committed_settings
    async with authenticated(settings, monkeypatch) as (one, h1, db):
        async with db.sessions.begin() as session:
            d = Discipline(
                id=uuid4(),
                slug=uuid4().hex,
                title="SYNTHETIC TWO ADMINS",
                icon_key="test",
                color_token="blue",
                status="published",
            )
            session.add(d)
            await session.flush()
            t = Topic(
                id=uuid4(),
                discipline_id=d.id,
                slug=uuid4().hex,
                title="SYNTHETIC TOPIC",
                status="published",
            )
            session.add(t)
        r = await one.post(
            "/api/v1/admin/imports?format=xlsx",
            content=document("xlsx", [[d.slug, t.slug, "SYNTHETIC ONE QUESTION", "A", "B", "A"]]),
            headers={**h1, "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 201, r.text
        jid = r.json()["data"]["id"]
        worker = Worker(settings)
        try:
            await worker.run_once()
        finally:
            await worker.close()
        async with authenticated(settings, monkeypatch) as (two, h2, db2):
            p1, p2 = await asyncio.gather(
                one.get(f"/api/v1/admin/imports/{jid}/publication-preview"),
                two.get(f"/api/v1/admin/imports/{jid}/publication-preview"),
            )

            async def send(client, headers, preview):
                assert preview.status_code == 200, preview.text
                p = preview.json()["data"]
                return await client.post(
                    f"/api/v1/admin/imports/{jid}/publish",
                    json={
                        "confirm": True,
                        "preview_hash": p["preview_hash"],
                        "file_sha256": p["file_sha256"],
                        "template_version": 1,
                        "selected_positions": [1],
                    },
                    headers={
                        **headers,
                        "If-Match": preview.headers["etag"],
                        "Idempotency-Key": str(uuid4()),
                    },
                )

            responses = await asyncio.gather(send(one, h1, p1), send(two, h2, p2))
            assert sorted(r.status_code for r in responses) == [200, 409], [
                r.text for r in responses
            ]
            from app.publishing.models import PublicationRun

            async with db.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(PublicationRun)) == 1
