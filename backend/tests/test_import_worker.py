"""Actual PostgreSQL, authenticated HTTP and isolated parser subprocesses."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update

from app.content.models import (
    Asset,
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.identity.models import UserRole
from app.imports.models import ImportContentKey, ImportJob, ImportRow
from app.imports.templates import MINIMAL_HEADERS, document
from app.imports.worker import Cancelled, LeaseLost, Worker

pytestmark = pytest.mark.integration


@pytest.fixture
async def context(admin_clients, database, tmp_path):
    async with admin_clients() as actor:
        settings = actor.settings.model_copy(update={"import_storage_dir": tmp_path / "private"})
        actor.app.state.settings = settings
        worker = Worker(settings)
        did, tid = uuid4(), uuid4()
        async with database.sessions.begin() as db:
            d = Discipline(
                id=did,
                slug=uuid4().hex,
                title="IMPORT TEST",
                icon_key="test",
                color_token="blue",
                status="draft",
            )
            db.add(d)
            await db.flush()
            t = Topic(
                id=tid, discipline_id=did, slug=uuid4().hex, title="IMPORT TOPIC", status="draft"
            )
            db.add(t)
        try:
            yield actor, worker, d, t
        finally:
            await worker.close()
            async with database.sessions.begin() as db:
                qs = select(Question.id).where(
                    Question.external_source == "import-topic:" + str(tid)
                )
                revs = select(QuestionRevision.id).where(QuestionRevision.question_id.in_(qs))
                jobs = select(ImportJob.id).where(ImportJob.created_by == actor.user_id)
                assets = list(
                    (
                        await db.scalars(
                            select(ImportJob.asset_id).where(ImportJob.created_by == actor.user_id)
                        )
                    ).all()
                )
                await db.execute(delete(ImportRow).where(ImportRow.import_job_id.in_(jobs)))
                await db.execute(delete(ImportContentKey).where(ImportContentKey.topic_id == tid))
                await db.execute(delete(TopicQuestion).where(TopicQuestion.question_id.in_(qs)))
                await db.execute(delete(QuestionOption).where(QuestionOption.revision_id.in_(revs)))
                await db.execute(
                    delete(QuestionRevision).where(QuestionRevision.question_id.in_(qs))
                )
                await db.execute(delete(Question).where(Question.id.in_(qs)))
                await db.execute(delete(ImportJob).where(ImportJob.created_by == actor.user_id))
                await db.execute(delete(Asset).where(Asset.id.in_(assets)))


def row(d, t, question="SYNTHETIC IMPORT", correct="A"):
    return [d.slug, t.slug, question, "First", "Second", correct]


async def upload(actor, raw, fmt="xlsx"):
    response = await actor.client.post(
        "/api/v1/admin/imports",
        params={"format": fmt},
        content=raw,
        headers={**actor.headers, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


async def result(actor, job):
    response = await actor.client.get("/api/v1/admin/imports/" + job["id"])
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("fmt", ["xlsx", "docx"])
async def test_real_upload_worker_preview_dedup_and_draft_only(context, fmt):
    a, w, d, t = context
    raw = document(fmt, [row(d, t), row(d, t), row(d, t, "INVALID", "Z")])
    job = await upload(a, raw, fmt)
    assert job["status"] == "queued"
    assert (await upload(a, raw, fmt))["id"] == job["id"]
    assert await w.run_once()
    done = await result(a, job)
    assert done["status"] == "completed", done
    assert (
        done["found"],
        done["valid"],
        done["errors"],
        done["drafts_created"],
        done["possible_duplicates"],
    ) == (3, 2, 1, 1, 1)
    rows = await a.client.get(f"/api/v1/admin/imports/{job['id']}/rows?limit=1")
    assert rows.status_code == 200, rows.text
    page = rows.json()["data"]
    assert page["page"]["has_more"]
    assert (
        await a.client.get(
            f"/api/v1/admin/imports/{job['id']}/rows",
            params={"cursor": page["page"]["next_cursor"]},
        )
    ).status_code == 200
    report = await a.client.get(f"/api/v1/admin/imports/{job['id']}/report")
    assert report.status_code == 200 and "Укажите букву" in report.text
    assert "storage_key" not in rows.text
    async with w.database.sessions() as db:
        revisions = list(
            (
                await db.scalars(
                    select(QuestionRevision).where(QuestionRevision.created_by == a.user_id)
                )
            ).all()
        )
        assert len(revisions) == 1 and revisions[0].status == "draft"
        q = await db.get(Question, revisions[0].question_id)
        assert q.current_revision_id is None and revisions[0].source_reference is None
    # Same contents in a different OOXML format are still deduplicated.
    other = "docx" if fmt == "xlsx" else "xlsx"
    nextjob = await upload(a, document(other, [row(d, t)]), other)
    await w.run_once()
    assert (await result(a, nextjob))["drafts_created"] == 0


async def test_explicit_key_versions_and_optional_metadata(context):
    a, w, d, t = context
    headers = [
        *MINIMAL_HEADERS,
        "external_id",
        "license_reference",
        "source_reference",
        "source_page",
        "explanation",
    ]
    first = await upload(a, document("xlsx", [[*row(d, t), "same-id", "", "", "", ""]], headers))
    await w.run_once()
    assert (await result(a, first))["drafts_created"] == 1
    second = await upload(
        a,
        document(
            "xlsx",
            [
                [
                    *row(d, t, "EDITED SYNTHETIC"),
                    "same-id",
                    "optional license",
                    "",
                    "",
                    "optional explanation",
                ]
            ],
            headers,
        ),
    )
    await w.run_once()
    done = await result(a, second)
    assert done["status"] == "completed" and done["drafts_created"] == 1, done
    async with w.database.sessions() as db:
        revs = list(
            (
                await db.scalars(
                    select(QuestionRevision)
                    .where(QuestionRevision.created_by == a.user_id)
                    .order_by(QuestionRevision.revision_number)
                )
            ).all()
        )
        assert [r.revision_number for r in revs] == [1, 2]
        assert revs[1].license_reference == "optional license"
        assert len({r.question_id for r in revs}) == 1
        assert all(r.status == "draft" for r in revs)


async def test_conflicting_file_keys_never_create_questions(context):
    a, w, d, t = context
    job = await upload(
        a,
        document(
            "xlsx",
            [[*row(d, t, "ONE"), "same"], [*row(d, t, "TWO"), "same"]],
            [*MINIMAL_HEADERS, "external_id"],
        ),
    )
    await w.run_once()
    done = await result(a, job)
    assert done["errors"] == 2 and done["drafts_created"] == 0, done


async def test_cancel_queued_retry_expired_lease_fences_old_worker(context):
    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t)]))
    url = "/api/v1/admin/imports/" + job["id"]
    assert (await a.client.post(url + "/cancel", headers=a.headers)).status_code == 200
    assert (await result(a, job))["status"] == "cancelled"
    assert (await a.client.post(url + "/retry", headers=a.headers)).status_code == 200
    claim = await w.claim()
    assert claim is not None
    jid, oldtoken = claim
    async with w.database.sessions.begin() as db:
        await db.execute(
            update(ImportJob)
            .where(ImportJob.id == jid)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    newclaim = await w.claim()
    assert newclaim and newclaim[0] == jid and newclaim[1] != oldtoken
    with pytest.raises(LeaseLost):
        await w.heartbeat(jid, oldtoken)
    await w.process(*newclaim)
    assert (await result(a, job))["drafts_created"] == 1
    # Replaying a stale worker cannot modify a completed job.
    await w.process(jid, oldtoken)
    assert (await result(a, job))["drafts_created"] == 1


async def test_partial_failure_batch_rollback_restart_no_duplicate_revisions(context, monkeypatch):
    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t, f"SYNTHETIC {i}") for i in range(3)]))
    monkeypatch.setattr("app.imports.worker.BATCH", 1)
    original = w.apply_row

    async def fail(db, job, row, roles):
        if row.position == 2:
            await original(db, job, row, roles)
            raise RuntimeError("synthetic failure after flush")
        await original(db, job, row, roles)

    monkeypatch.setattr(w, "apply_row", fail)
    await w.run_once()
    done = await result(a, job)
    assert done["status"] == "failed" and done["drafts_created"] == 1, done
    monkeypatch.setattr(w, "apply_row", original)
    assert (
        await a.client.post("/api/v1/admin/imports/" + job["id"] + "/retry", headers=a.headers)
    ).status_code == 200
    await w.run_once()
    done = await result(a, job)
    assert done["status"] == "completed" and done["drafts_created"] == 3, done
    async with w.database.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(QuestionRevision)
                .where(QuestionRevision.created_by == a.user_id)
            )
            == 3
        )


async def test_cancel_processing_and_role_revocation(context, monkeypatch):
    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t)]))
    claim = await w.claim()
    assert claim
    await a.client.post("/api/v1/admin/imports/" + job["id"] + "/cancel", headers=a.headers)
    with pytest.raises(Cancelled):
        await w.heartbeat(*claim)
    await w.process(*claim)
    assert (await result(a, job))["status"] == "cancelled"
    await a.client.post("/api/v1/admin/imports/" + job["id"] + "/retry", headers=a.headers)
    async with w.database.sessions.begin() as db:
        await db.execute(delete(UserRole).where(UserRole.user_id == a.user_id))
    await w.run_once()
    async with w.database.sessions() as db:
        stored = await db.get(ImportJob, UUID(job["id"]))
        assert stored.status == "failed" and stored.error_code == "ACCESS_REVOKED"


async def test_owner_admin_mfa_csrf_and_private_raw_files(context, admin_clients):
    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t)]))
    for role, confirmed, expected in [
        ("student", False, 403),
        ("content_reviewer", True, 403),
        ("content_editor", False, 403),
    ]:
        async with admin_clients(role, confirmed=confirmed) as other:
            response = await other.client.get("/api/v1/admin/imports")
            assert response.status_code == expected, response.text
    async with admin_clients() as other:
        for suffix in ("", "/rows", "/report"):
            assert (
                await other.client.get("/api/v1/admin/imports/" + job["id"] + suffix)
            ).status_code == 404
        assert (
            await other.client.post(
                "/api/v1/admin/imports/" + job["id"] + "/cancel", headers=other.headers
            )
        ).status_code == 404
    response = await a.client.post(
        "/api/v1/admin/imports?format=xlsx",
        content=document("xlsx", [row(d, t)]),
        headers={"Origin": a.headers["Origin"], "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 403, response.text
    for fmt in ("xlsx", "docx"):
        response = await a.client.get("/api/v1/admin/import-templates/" + fmt)
        assert response.status_code == 200 and response.content[:2] == b"PK"
    async with w.database.sessions() as db:
        asset = await db.get(Asset, (await db.get(ImportJob, UUID(job["id"]))).asset_id)
        assert (await a.client.get(f"/api/v1/assets/{asset.id}")).status_code == 404
        assert w.store.path(asset.storage_key).stat().st_mode & 0o077 == 0


async def test_large_streams_allowed_only_import_route_and_bounded(context):
    a, w, d, t = context
    import io
    import zipfile

    raw = io.BytesIO(document("xlsx", [row(d, t)]))
    with zipfile.ZipFile(raw, "a", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("docProps/extra.xml", b"<x>" + b" " * 40000 + b"</x>")
    assert len(raw.getvalue()) > 32768
    job = await upload(a, raw.getvalue())
    assert job["status"] == "queued"

    async def chunks():
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    response = await a.client.post(
        "/api/v1/admin/imports?format=xlsx",
        content=chunks(),
        headers={**a.headers, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413, response.text
    assert len(list(w.store.root.iterdir())) == 1
    response = await a.client.post("/api/v1/users/me", content=b"x" * 40000, headers=a.headers)
    assert response.status_code == 413


async def test_tampered_file_zip_bomb_and_hash_fail_before_any_draft(context):
    import io
    import zipfile

    a, w, d, t = context
    raw = io.BytesIO(document("xlsx", [row(d, t)]))
    with zipfile.ZipFile(raw, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/oversized.xml", b" " * 2_000_000)
    job = await upload(a, raw.getvalue())
    await w.run_once()
    assert (await result(a, job))["error_code"] == "ZIP_LIMIT"
    nextjob = await upload(a, document("docx", [row(d, t)]), "docx")
    async with w.database.sessions() as db:
        asset = await db.get(Asset, (await db.get(ImportJob, UUID(nextjob["id"]))).asset_id)
        w.store.path(asset.storage_key).write_bytes(b"tampered")
    await w.run_once()
    done = await result(a, nextjob)
    assert done["error_code"] == "FILE_HASH" and done["drafts_created"] == 0


async def test_worker_singleton_lock_and_cancellation_kills_real_parser(context, monkeypatch):
    from sqlalchemy import text

    from app.imports.worker import WORKER_LOCK

    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t)]))
    async with w.database.engine.connect() as connection:
        await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": WORKER_LOCK})
        await connection.commit()
        try:
            assert await w.run_once() is False
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK})
            await connection.commit()
    original = w.heartbeat

    async def cancel(jid, token):
        await a.client.post("/api/v1/admin/imports/" + str(jid) + "/cancel", headers=a.headers)
        await original(jid, token)

    monkeypatch.setattr(w, "heartbeat", cancel)
    await w.run_once()
    assert (await result(a, job))["status"] == "cancelled"
    assert not list(w.store.root.glob("work-*"))


async def test_private_drafts_cannot_be_overwritten_by_other_editor(context, admin_clients):
    a, w, d, t = context
    headers = [*MINIMAL_HEADERS, "external_id"]
    job = await upload(a, document("xlsx", [[*row(d, t), "private-id"]], headers))
    await w.run_once()
    async with admin_clients() as other:
        other.app.state.settings = a.app.state.settings
        second = await upload(
            other, document("xlsx", [[*row(d, t, "CHANGED BY OTHER"), "private-id"]], headers)
        )
        try:
            await w.run_once()
            done = await result(other, second)
            assert done["errors"] == 1 and done["drafts_created"] == 0
            response = await other.client.get("/api/v1/admin/imports/" + second["id"] + "/rows")
            assert response.json()["data"]["items"][0]["draft_revision_id"] is None
        finally:
            async with w.database.sessions.begin() as db:
                stored = await db.get(ImportJob, UUID(second["id"]))
                aid = stored.asset_id
                await db.execute(delete(ImportRow).where(ImportRow.import_job_id == stored.id))
                await db.delete(stored)
                await db.flush()
                await db.execute(delete(Asset).where(Asset.id == aid))
    assert (await result(a, job))["drafts_created"] == 1


async def test_retention_keeps_drafts_reports_and_unexpired_sources(context):
    import os

    from app.imports.cleanup import cleanup

    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t)]))
    await w.run_once()
    async with w.database.sessions.begin() as db:
        stored = await db.get(ImportJob, UUID(job["id"]))
        asset = await db.get(Asset, stored.asset_id)
        path = w.store.path(asset.storage_key)
        stored.updated_at = datetime.now(UTC) - timedelta(days=31)
    orphan = w.store.path("f" * 32)
    orphan.write_bytes(b"orphan")
    expired = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(orphan, (expired, expired))
    assert await cleanup(w) == 2
    assert not path.exists() and not orphan.exists()
    assert (await result(a, job))["drafts_created"] == 1
    report = await a.client.get("/api/v1/admin/imports/" + job["id"] + "/report")
    assert report.status_code == 200
    # Retention cannot be bypassed using retry.
    response = await a.client.post(
        "/api/v1/admin/imports/" + job["id"] + "/retry", headers=a.headers
    )
    assert response.status_code == 409


async def test_multiple_atomic_hundred_row_batches_and_exhausted_retries(context):
    a, w, d, t = context
    job = await upload(a, document("xlsx", [row(d, t, f"SYNTHETIC BATCH {i}") for i in range(205)]))
    await w.run_once()
    done = await result(a, job)
    assert done["status"] == "completed" and done["drafts_created"] == 205, done
    async with w.database.sessions.begin() as db:
        stored = await db.get(ImportJob, UUID(job["id"]))
        stored.status = "failed"
        stored.attempts = 3
    response = await a.client.post(
        "/api/v1/admin/imports/" + job["id"] + "/retry", headers=a.headers
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "IMPORT_ATTEMPTS"


async def test_expired_mfa_rejected_before_stream_is_read(context):
    a, w, d, t = context
    consumed = False

    async def stream():
        nonlocal consumed
        consumed = True
        yield document("xlsx", [row(d, t)])

    a.clock[0] += timedelta(minutes=16)
    response = await a.client.post(
        "/api/v1/admin/imports?format=xlsx",
        content=stream(),
        headers={**a.headers, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 403 and not consumed, response.text
    assert not list(w.store.root.iterdir())


async def test_imported_drafts_never_enter_public_reference_catalog(context):
    a, w, d, t = context
    async with w.database.sessions.begin() as db:
        await db.execute(update(Discipline).where(Discipline.id == d.id).values(status="published"))
        await db.execute(update(Topic).where(Topic.id == t.id).values(status="published"))
    job = await upload(a, document("xlsx", [row(d, t)]))
    await w.run_once()
    assert (await result(a, job))["drafts_created"] == 1
    response = await a.client.get(f"/api/v1/topics/{t.id}/reference-questions")
    assert response.status_code == 200 and response.json()["data"] == [], response.text
