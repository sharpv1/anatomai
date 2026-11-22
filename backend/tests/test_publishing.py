"""Publication history is tested in rollback-only outer transactions, never deleted."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.content.models import Discipline, Question, QuestionOption, QuestionRevision, Topic
from app.db.models import IdempotencyRequest
from app.identity.models import UserRole
from app.imports.models import ImportJob, ImportRow
from app.imports.templates import document
from app.imports.worker import LeaseLost, Worker, now
from app.publishing.models import PublicationCommand, PublicationItem, PublicationRun
from app.publishing.worker import PublishingWorker

pytestmark = pytest.mark.integration


@pytest.fixture
async def context(admin_clients, database, tmp_path):
    async with admin_clients("admin") as a:
        settings = a.settings.model_copy(update={"import_storage_dir": tmp_path / "private"})
        a.app.state.settings = settings
        async with database.engine.connect() as connection:
            outer = await connection.begin()
            sessions = async_sessionmaker(
                connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            previous = a.app.state.database.sessions
            a.app.state.database.sessions = sessions
            importer = Worker(settings)
            worker = PublishingWorker(settings)
            importer.database.sessions = sessions
            worker.database.sessions = sessions
            async with sessions.begin() as db:
                d = Discipline(
                    id=uuid4(),
                    slug=uuid4().hex,
                    title="SYNTHETIC PUBLISH",
                    icon_key="test",
                    color_token="blue",
                    status="published",
                )
                db.add(d)
                await db.flush()
                t = Topic(
                    id=uuid4(),
                    discipline_id=d.id,
                    slug=uuid4().hex,
                    title="SYNTHETIC TOPIC",
                    status="published",
                )
                db.add(t)
            try:
                yield a, importer, worker, d, t, sessions
            finally:
                await worker.close()
                await importer.close()
                await outer.rollback()
                a.app.state.database.sessions = previous


async def imported(c, count=1, invalid=False):
    a, imp, w, d, t, sessions = c
    rows = [
        [d.slug, t.slug, f"SYNTHETIC QUESTION {i}", "First", "Second", "A"] for i in range(count)
    ]
    if invalid:
        rows.append([d.slug, t.slug, "INVALID", "A", "B", "Z"])
    r = await a.client.post(
        "/api/v1/admin/imports?format=xlsx",
        content=document("xlsx", rows),
        headers={**a.headers, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 201, r.text
    jid = r.json()["data"]["id"]
    assert await imp.run_once()
    r = await a.client.get("/api/v1/admin/imports/" + jid)
    assert r.json()["data"]["status"] == "completed", r.text
    return jid


async def preview(a, jid):
    r = await a.client.get(f"/api/v1/admin/imports/{jid}/publication-preview")
    assert r.status_code == 200, r.text
    return r.json()["data"], r.headers["etag"]


async def confirm(a, jid, positions=None, key=None, previous=None):
    p, etag = previous or await preview(a, jid)
    body = {
        "confirm": True,
        "preview_hash": p["preview_hash"],
        "file_sha256": p["file_sha256"],
        "template_version": 1,
        "selected_positions": positions or p["eligible_positions"],
    }
    headers = {**a.headers, "If-Match": etag, "Idempotency-Key": key or str(uuid4())}
    r = await a.client.post(f"/api/v1/admin/imports/{jid}/publish", json=body, headers=headers)
    return r, body, headers


async def report(a, pid):
    r = await a.client.get("/api/v1/admin/publications/" + pid)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def revision_action(a, rid, action, key=None, previous=None):
    p = previous or await a.client.get(
        f"/api/v1/admin/question-revisions/{rid}/publication-preview"
    )
    assert p.status_code == 200, p.text
    body = {"confirm": True, "preview_hash": p.json()["data"]["preview_hash"]}
    if action != "publish":
        body["reason"] = "SYNTHETIC EXPLICIT ACTION"
    headers = {**a.headers, "If-Match": p.headers["etag"], "Idempotency-Key": key or str(uuid4())}
    r = await a.client.post(
        f"/api/v1/admin/question-revisions/{rid}/{action}", json=body, headers=headers
    )
    return r, body, headers


async def rev_id(c, jid, position=1):
    async with c[-1]() as db:
        return str(
            await db.scalar(
                select(ImportRow.applied_revision_id).where(
                    ImportRow.import_job_id == UUID(jid), ImportRow.position == position
                )
            )
        )


async def test_import_confirm_single_choice_no_sources_no_reviewer_and_public_catalog(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 3, invalid=True)
    p, _ = await preview(a, jid)
    assert (p["found"], p["valid"], p["errors"], p["publishable"]) == (4, 3, 1, 3)
    r, body, headers = await confirm(a, jid)
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["publication_id"]
    assert (await a.client.get(f"/api/v1/topics/{t.id}/reference-questions")).json()["data"] == []
    assert await w.run_once()
    done = await report(a, pid)
    assert done["status"] == "completed" and done["counts"]["published"] == 3, done
    public = await a.client.get(f"/api/v1/topics/{t.id}/reference-questions")
    assert public.status_code == 200 and len(public.json()["data"]) == 3, public.text
    replay = await a.client.post(f"/api/v1/admin/imports/{jid}/publish", json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["data"] == r.json()["data"]
    async with sessions() as db:
        for rev in (
            await db.scalars(
                select(QuestionRevision).where(
                    QuestionRevision.id.in_([UUID(item["revision_id"]) for item in done["items"]])
                )
            )
        ).all():
            assert (
                rev.source_id is None
                and rev.medical_review_by is None
                and rev.status == "published"
            )


async def test_invalid_selection_hash_file_template_and_duplicates(context):
    c = context
    a = c[0]
    jid = await imported(c, 1, invalid=True)
    r, _, _ = await confirm(a, jid, [1, 2])
    assert r.status_code == 409
    p, etag = await preview(a, jid)
    for change in (
        {"preview_hash": "0" * 64},
        {"file_sha256": "0" * 64},
        {"selected_positions": [1, 1]},
        {"confirm": 1},
        {"template_version": 2},
    ):
        body = {
            "confirm": True,
            "preview_hash": p["preview_hash"],
            "file_sha256": p["file_sha256"],
            "template_version": 1,
            "selected_positions": [1],
            **change,
        }
        response = await a.client.post(
            f"/api/v1/admin/imports/{jid}/publish",
            json=body,
            headers={**a.headers, "If-Match": etag, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code in (409, 422), response.text


async def test_direct_publish_withdraw_restore_preserves_history_and_option_ids(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    rid = await rev_id(c, jid)
    r, body, headers = await revision_action(a, rid, "publish")
    assert r.status_code == 200, r.text
    async with sessions() as db:
        qid = await db.scalar(
            select(QuestionRevision.question_id).where(QuestionRevision.id == UUID(rid))
        )
        oldopts = list(
            (
                await db.scalars(
                    select(QuestionOption.id).where(QuestionOption.revision_id == UUID(rid))
                )
            ).all()
        )
    r, _, _ = await revision_action(a, rid, "withdraw")
    assert r.status_code == 200, r.text
    assert (await a.client.get(f"/api/v1/topics/{t.id}/reference-questions")).json()["data"] == []
    r, restorebody, restoreheaders = await revision_action(a, rid, "restore")
    assert r.status_code == 200, r.text
    newrid = UUID(r.json()["data"]["revision_id"])
    assert str(newrid) != rid and r.json()["data"]["outcome"] == "restored_copy"
    async with sessions() as db:
        original = await db.get(QuestionRevision, UUID(rid))
        copy = await db.get(QuestionRevision, newrid)
        assert (
            original.status == "withdrawn"
            and copy.status == "published"
            and original.text == copy.text
        )
        assert (await db.get(Question, qid)).current_revision_id == newrid
        assert set(oldopts).isdisjoint(
            (
                await db.scalars(
                    select(QuestionOption.id).where(QuestionOption.revision_id == newrid)
                )
            ).all()
        )
    replay = await a.client.post(
        f"/api/v1/admin/question-revisions/{rid}/restore", json=restorebody, headers=restoreheaders
    )
    assert replay.json()["data"]["revision_id"] == str(newrid)
    # Even after the generic 7-day key cache expires, permanent receipt prevents another copy.
    async with sessions.begin() as db:
        await db.execute(
            update(IdempotencyRequest)
            .where(IdempotencyRequest.actor_id == a.user_id)
            .values(created_at=now() - timedelta(days=9), expires_at=now() - timedelta(days=1))
        )
    replay = await a.client.post(
        f"/api/v1/admin/question-revisions/{rid}/restore", json=restorebody, headers=restoreheaders
    )
    assert replay.status_code == 200 and replay.json()["data"]["revision_id"] == str(newrid), (
        replay.text
    )


async def test_stale_draft_catalog_and_idempotency_payloads_rejected(context):
    c = context
    a = c[0]
    jid = await imported(c)
    rid = await rev_id(c, jid)
    old = await a.client.get(f"/api/v1/admin/question-revisions/{rid}/publication-preview")
    async with c[-1].begin() as db:
        rev = await db.get(QuestionRevision, UUID(rid))
        rev.text = "EDITED AFTER PREVIEW"
    r, _, _ = await revision_action(a, rid, "publish", previous=old)
    assert r.status_code in (409, 412), r.text
    r, body, headers = await revision_action(a, rid, "publish")
    assert r.status_code == 200, r.text
    altered = {**body, "preview_hash": "0" * 64}
    r = await a.client.post(
        f"/api/v1/admin/question-revisions/{rid}/publish", json=altered, headers=headers
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_batch_atomic_failure_partial_retry_and_new_ids_not_duplicated(context, monkeypatch):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 3)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    monkeypatch.setattr("app.publishing.worker.BATCH", 1)
    from app.publishing.worker import publish_one

    calls = []

    async def fail(db, rid, actor, request_id):
        calls.append(rid)
        result = await publish_one(db, rid, actor, request_id)
        if len(calls) == 2:
            raise RuntimeError("synthetic fault after flush")
        return result

    monkeypatch.setattr("app.publishing.worker.publish_one", fail)
    await w.run_once()
    done = await report(a, pid)
    assert (
        done["status"] == "failed"
        and done["counts"]["published"] == 1
        and done["counts"]["pending"] == 2
    ), done
    monkeypatch.setattr("app.publishing.worker.publish_one", publish_one)
    retry = await a.client.post(f"/api/v1/admin/publications/{pid}/retry", headers=a.headers)
    assert retry.status_code == 200, retry.text
    await w.run_once()
    done = await report(a, pid)
    assert done["status"] == "completed" and done["counts"]["published"] == 3, done


async def test_staging_freeze_and_worker_detects_changed_draft(context):
    from sqlalchemy.exc import DBAPIError

    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 2)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    async with sessions.begin() as db:
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    update(ImportRow)
                    .where(ImportRow.import_job_id == UUID(jid))
                    .values(topic="TAMPER")
                )
        rev = await db.get(QuestionRevision, UUID(await rev_id(c, jid)))
        rev.text = "CHANGED AFTER CONFIRMATION"
    await w.run_once()
    done = await report(a, pid)
    assert (
        done["status"] == "failed"
        and done["error_code"] == "STALE_ITEM"
        and done["counts"]["published"] == 0
    ), done
    retry = await a.client.post(f"/api/v1/admin/publications/{pid}/retry", headers=a.headers)
    assert retry.status_code == 409


async def test_cancel_and_stale_worker_fencing(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    r = await a.client.post(f"/api/v1/admin/publications/{pid}/cancel", headers=a.headers)
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    assert (
        await a.client.post(f"/api/v1/admin/publications/{pid}/retry", headers=a.headers)
    ).status_code == 200
    first = await w.claim()
    assert first
    async with sessions.begin() as db:
        run = await db.get(PublicationRun, UUID(pid))
        run.lease_until = now() - timedelta(seconds=1)
    second = await w.claim()
    assert second and first[1] != second[1]
    with pytest.raises(LeaseLost):
        await w.heartbeat(*first)
    await w.process(*second)
    assert (await report(a, pid))["counts"]["published"] == 1


async def test_multiple_choice_and_role_revocation_are_blocked(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    async with sessions.begin() as db:
        await db.execute(
            __import__("sqlalchemy").delete(UserRole).where(UserRole.user_id == a.user_id)
        )
    await w.run_once()
    async with sessions() as db:
        run = await db.get(PublicationRun, UUID(pid))
        assert run.status == "failed" and run.error_code == "ACCESS_REVOKED"


async def test_csrf_mfa_rbac_and_editor_ownership(context, admin_clients):
    c = context
    a = c[0]
    jid = await imported(c)
    rid = await rev_id(c, jid)
    p, etag = await preview(a, jid)
    async with admin_clients("content_editor") as editor:
        # Use same rollback-only database view for negative ownership checks.
        editor.app.state.database.sessions = c[-1]
        assert (
            await editor.client.get(f"/api/v1/admin/imports/{jid}/publication-preview")
        ).status_code == 403
        assert (
            await editor.client.get(f"/api/v1/admin/question-revisions/{rid}/publication-preview")
        ).status_code == 404
    r = await a.client.post(
        f"/api/v1/admin/imports/{jid}/publish",
        json={
            "confirm": True,
            "preview_hash": p["preview_hash"],
            "file_sha256": p["file_sha256"],
            "template_version": 1,
            "selected_positions": [1],
        },
        headers={"Origin": a.headers["Origin"], "If-Match": etag, "Idempotency-Key": str(uuid4())},
    )
    assert r.status_code == 403
    a.clock[0] += timedelta(minutes=16)
    assert (
        await a.client.get(f"/api/v1/admin/imports/{jid}/publication-preview")
    ).status_code == 403


async def test_editor_publishes_own_draft_and_reviewer_cannot(context, admin_clients):
    c = context
    jid = await imported(c)
    rid = await rev_id(c, jid)
    async with admin_clients("content_editor") as editor:
        editor.app.state.database.sessions = c[-1]
        async with c[-1].begin() as db:
            rev = await db.get(QuestionRevision, UUID(rid))
            rev.created_by = editor.user_id
        r, _, _ = await revision_action(editor, rid, "publish")
        assert r.status_code == 200, r.text
    async with admin_clients("content_reviewer") as reviewer:
        reviewer.app.state.database.sessions = c[-1]
        assert (
            await reviewer.client.get(f"/api/v1/admin/question-revisions/{rid}/publication-preview")
        ).status_code == 403


async def test_multiple_choice_and_zero_correct_are_not_publishable(context):
    c = context
    a = c[0]
    jid = await imported(c, 2)
    async with c[-1].begin() as db:
        first = await db.get(QuestionRevision, UUID(await rev_id(c, jid, 1)))
        first.kind = "multiple_choice"
        await db.execute(
            update(QuestionOption)
            .where(QuestionOption.revision_id == UUID(await rev_id(c, jid, 2)))
            .values(is_correct=False)
        )
    for position in (1, 2):
        r, _, _ = await revision_action(a, await rev_id(c, jid, position), "publish")
        assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_PUBLISHABLE", r.text


async def test_catalog_cursor_invalidated_and_repeat_restore_is_noop(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 3)
    r, _, _ = await confirm(a, jid)
    await w.run_once()
    page = await a.client.get(f"/api/v1/topics/{t.id}/reference-questions?limit=1")
    cursor = page.json()["page"]["next_cursor"]
    assert cursor
    rid = await rev_id(c, jid)
    r, _, _ = await revision_action(a, rid, "withdraw")
    assert r.status_code == 200
    oldpage = await a.client.get(
        f"/api/v1/topics/{t.id}/reference-questions", params={"cursor": cursor}
    )
    assert oldpage.status_code == 409 and oldpage.json()["error"]["code"] == "CATALOG_CHANGED"
    first, _, _ = await revision_action(a, rid, "restore")
    second, _, _ = await revision_action(a, rid, "restore")
    assert first.json()["data"]["revision_id"] == second.json()["data"]["revision_id"]
    assert second.json()["data"]["outcome"] == "unchanged"


async def test_file_changed_after_confirmation_never_publishes(context):
    from app.content.models import Asset

    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    async with sessions() as db:
        job = await db.get(ImportJob, UUID(jid))
        asset = await db.get(Asset, job.asset_id)
        path = w.store.path(asset.storage_key)
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    await w.run_once()
    done = await report(a, pid)
    assert (
        done["status"] == "failed"
        and done["error_code"] == "FILE_CHANGED"
        and done["counts"]["published"] == 0
    )


async def test_205_questions_publish_in_real_hundred_item_batches(context):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 205)
    r, _, _ = await confirm(a, jid)
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["publication_id"]
    await w.run_once()
    done = await report(a, pid)
    assert done["status"] == "completed" and done["counts"]["published"] == 205, done


async def test_restore_previous_published_pointer_and_exam_safe_dto(context):
    from app.content.models import TestDefinition

    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    rid = await rev_id(c, jid)
    r, _, _ = await revision_action(a, rid, "publish")
    qid = r.json()["data"]["question_id"]
    body = {
        "text": "NEW SYNTHETIC VERSION",
        "options": [
            {"code": "A", "text": "First", "is_correct": True},
            {"code": "B", "text": "Second", "is_correct": False},
        ],
    }
    r = await a.client.post(
        f"/api/v1/admin/questions/{qid}/revisions", json=body, headers=await a.write_headers()
    )
    assert r.status_code == 201, r.text
    newrid = r.json()["data"]["id"]
    r, _, _ = await revision_action(a, newrid, "publish")
    assert r.status_code == 200, r.text
    r, _, _ = await revision_action(a, rid, "restore")
    assert r.status_code == 200 and r.json()["data"]["outcome"] == "restored", r.text
    definition = uuid4()
    async with sessions.begin() as db:
        assert (await db.get(Question, UUID(qid))).current_revision_id == UUID(rid)
        assert (await db.get(QuestionRevision, UUID(newrid))).status == "published"
        db.add(
            TestDefinition(
                id=definition,
                topic_id=t.id,
                slug=uuid4().hex,
                title="SYNTHETIC EXAM",
                exam_duration_seconds=60,
                status="published",
            )
        )
    safe = await a.client.get(f"/api/v1/test-definitions/{definition}/questions")
    assert safe.status_code == 200, safe.text
    assert len(safe.json()["data"]) == 1
    for forbidden in ("is_correct", "correct_option_ids", "explanation", "medical_review_by"):
        assert forbidden not in safe.text


async def test_confirmation_receipts_snapshots_and_downgrade_are_immutable(context):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import DBAPIError

    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    r, _, _ = await confirm(a, jid)
    pid = UUID(r.json()["data"]["publication_id"])
    async with sessions.begin() as db:
        for statement in (
            update(PublicationItem).where(PublicationItem.run_id == pid).values(snapshot={}),
            update(PublicationRun).where(PublicationRun.id == pid).values(file_sha256="0" * 64),
            update(PublicationCommand).values(result={}),
            text("TRUNCATE publication_commands"),
            update(ImportJob).where(ImportJob.id == UUID(jid)).values(template_version=2),
        ):
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(statement)
        path = Path(__file__).resolve().parents[1] / "migrations/versions/0007_publishing.py"
        spec = importlib.util.spec_from_file_location("publishing_revision", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def down(conn):
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()

        connection = await db.connection()
        with pytest.raises(RuntimeError, match="permanent publication history"):
            await connection.run_sync(down)


async def test_cancel_during_processing_keeps_completed_batches(context, monkeypatch):
    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c, 3)
    r, _, _ = await confirm(a, jid)
    pid = r.json()["data"]["publication_id"]
    monkeypatch.setattr("app.publishing.worker.BATCH", 1)
    original = w.heartbeat

    async def cancel(run_id, token):
        r = await a.client.post(f"/api/v1/admin/publications/{run_id}/cancel", headers=a.headers)
        assert r.status_code == 200, r.text
        await original(run_id, token)

    monkeypatch.setattr(w, "heartbeat", cancel)
    await w.run_once()
    done = await report(a, pid)
    assert (
        done["status"] == "cancelled"
        and done["counts"]["published"] == 1
        and done["counts"]["pending"] == 2
    ), done


async def test_authorizing_session_removal_preserves_accepted_command(context):
    from sqlalchemy import delete

    from app.identity.models import AuthReplay, UserSession

    c = context
    a, imp, w, d, t, sessions = c
    jid = await imported(c)
    r, _, _ = await confirm(a, jid)
    pid = UUID(r.json()["data"]["publication_id"])
    async with sessions.begin() as db:
        run = await db.get(PublicationRun, pid)
        sid = run.authorized_session_id
        assert sid
        await db.execute(delete(AuthReplay).where(AuthReplay.session_id == sid))
        await db.execute(delete(UserSession).where(UserSession.id == sid))
        await db.refresh(run)
        job = await db.get(ImportJob, UUID(jid))
        assert run.authorized_session_id is None and job.authorized_session_id is None
    await w.run_once()
    async with sessions() as db:
        assert (await db.get(PublicationRun, pid)).status == "completed"


async def test_staging_payload_changed_after_preview_rejects_old_confirmation(context):
    c = context
    a = c[0]
    jid = await imported(c)
    old = await preview(a, jid)
    async with c[-1].begin() as db:
        row = await db.scalar(select(ImportRow).where(ImportRow.import_job_id == UUID(jid)))
        row.normalized_payload = {**row.normalized_payload, "text": "TAMPERED STAGING PAYLOAD"}
    response, _, _ = await confirm(a, jid, previous=old)
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "STALE_CONFIRMATION"
    ), response.text
    current, _ = await preview(a, jid)
    assert current["publishable"] == 0 and current["conflicts"] == 1
    assert current["blocked"] == [{"position": 1, "code": "REVISION_CHANGED"}]


async def test_fresh_confirmation_can_replace_exhausted_run_without_losing_history(context):
    c = context
    a = c[0]
    jid = await imported(c)
    response, body, headers = await confirm(a, jid)
    oldid = UUID(response.json()["data"]["publication_id"])
    async with c[-1].begin() as db:
        run = await db.get(PublicationRun, oldid)
        run.status = "failed"
        run.attempts = 3
        run.error_code = "LEASE_EXHAUSTED"
    retried = await a.client.post(f"/api/v1/admin/publications/{oldid}/retry", headers=a.headers)
    assert retried.status_code == 409
    fresh, _, _ = await confirm(a, jid)
    assert fresh.status_code == 200 and fresh.json()["data"]["publication_id"] != str(oldid), (
        fresh.text
    )
