"""Real PostgreSQL, HTTP auth/CSRF, rollback-only attempt history."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.attempts.models import Attempt, AttemptCommand, AttemptItem, AttemptOption, AttemptResponse
from app.content.models import Question, QuestionOption, QuestionRevision, TopicQuestion
from app.db.models import IdempotencyRequest

pytestmark = pytest.mark.integration


@pytest.fixture
async def context(admin_clients, database, content_data):
    async with admin_clients("student", confirmed=False, enrolled=False) as a:
        async with database.engine.connect() as conn:
            outer = await conn.begin()
            sessions = async_sessionmaker(
                conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            previous = a.app.state.database.sessions
            a.app.state.database.sessions = sessions
            try:
                yield a, sessions, content_data
            finally:
                await outer.rollback()
                a.app.state.database.sessions = previous


async def start(c, scope="topic", key=None):
    a, db, data = c
    body = {
        "topic": {"topic_id": str(data["topic"].id)},
        "discipline": {"discipline_id": str(data["d"].id)},
        "test": {"test_definition_id": str(data["definition"].id)},
    }[scope]
    headers = {**a.headers, "Idempotency-Key": key or str(uuid4())}
    r = await a.client.post("/api/v1/attempts", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r, body, headers


async def action(a, r, op, body=None, key=None):
    d = r.json()["data"]
    item = d["current_item"]
    url = f"/api/v1/attempts/{d['id']}/" + (f"items/{item['id']}/submit" if op == "submit" else op)
    if body is None:
        body = {"item_id": item["id"]} if op in ("advance", "skip") else {}
    h = {**a.headers, "If-Match": r.headers["etag"], "Idempotency-Key": key or str(uuid4())}
    result = await a.client.post(url, json=body, headers=h)
    return result, url, body, h


@pytest.mark.parametrize("scope", ["discipline", "topic", "test"])
async def test_start_snapshot_scopes_safe_dto_and_resume(context, scope):
    a, sessions, data = context
    r, _, _ = await start(context, scope)
    d = r.json()["data"]
    item = d["current_item"]
    assert d["total"] == 2 and d["version"] == 1 and d["mode"] == "learning"
    assert item["state"] == "awaiting_answer" and len(item["options"]) == 2
    for forbidden in ("is_correct", "correct_option_ids", "explanation", "result"):
        assert forbidden not in r.text
    assert item["revision_id"] == str(data["revisions"][0].id)
    assert [o["id"] for o in item["options"]] == [str(o.id) for o in data["options"][0]]
    resumed = await a.client.get("/api/v1/attempts/" + d["id"])
    assert resumed.json()["data"] == d and resumed.headers["etag"] == r.headers["etag"]
    active = await a.client.get("/api/v1/me/active-attempt")
    assert active.json()["data"]["id"] == d["id"]
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AttemptItem)
                .where(AttemptItem.attempt_id == UUID(d["id"]))
            )
            == 2
        )


async def test_submit_feedback_locked_no_wrong_option_and_replay(context):
    a, sessions, data = context
    r, _, _ = await start(context)
    item = r.json()["data"]["current_item"]
    wrong = await action(a, r, "submit", {"selected_option_ids": [str(data["options"][1][0].id)]})
    assert wrong[0].status_code == 422
    submitted, url, body, h = await action(
        a, r, "submit", {"selected_option_ids": [item["options"][1]["id"]]}
    )
    assert submitted.status_code == 200, submitted.text
    feedback = submitted.json()["data"]["current_item"]["feedback"]
    assert feedback["is_correct"] is False and feedback["correct_option_ids"] == [
        item["options"][0]["id"]
    ]
    assert feedback["explanation"] == "SECRET-EXPLANATION"
    locked = await action(
        a, submitted, "submit", {"selected_option_ids": [item["options"][0]["id"]]}
    )
    assert locked[0].status_code == 409 and locked[0].json()["error"]["code"] == "ANSWER_LOCKED"
    replay = await a.client.post(url, json=body, headers=h)
    assert replay.status_code == 200 and replay.json()["data"] == submitted.json()["data"]
    changed = await a.client.post(
        url, json={"selected_option_ids": [item["options"][0]["id"]]}, headers=h
    )
    assert (
        changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    )
    resumed = await a.client.get("/api/v1/attempts/" + r.json()["data"]["id"])
    assert resumed.json()["data"]["current_item"]["feedback"] == feedback


async def test_advance_requires_submit_skip_locks_and_last_item_finishes(context):
    a, _, _ = context
    r, _, _ = await start(context)
    advance = await action(a, r, "advance")
    assert advance[0].status_code == 409
    moved, url, body, h = await action(a, r, "skip")
    assert moved.status_code == 200 and moved.json()["data"]["current_position"] == 1, moved.text
    assert "explanation" not in moved.text and "correct_option_ids" not in moved.text
    replay = await a.client.post(url, json=body, headers=h)
    assert replay.json()["data"] == moved.json()["data"]
    done, _, _, _ = await action(a, moved, "skip")
    assert done.status_code == 200 and done.json()["data"]["status"] == "completed", done.text
    result = done.json()["data"]["result"]
    assert (result["correct"], result["wrong"], result["skipped"], result["percent"]) == (
        0,
        0,
        2,
        0,
    )
    assert done.json()["data"]["current_item"] is None
    assert (await a.client.get("/api/v1/me/active-attempt")).json()["data"] is None


async def test_finish_preserves_checked_answer_and_abandon_has_no_result(context):
    a, _, _ = context
    r, _, _ = await start(context)
    current = r.json()["data"]["current_item"]
    submitted, _, _, _ = await action(
        a, r, "submit", {"selected_option_ids": [current["options"][0]["id"]]}
    )
    await asyncio.sleep(1.05)
    done, url, body, h = await action(a, submitted, "finish")
    assert done.status_code == 200, done.text
    result = done.json()["data"]["result"]
    assert (result["correct"], result["wrong"], result["skipped"], result["percent"]) == (
        1,
        0,
        1,
        50,
    )
    assert result["duration_seconds"] >= 1
    replay = await a.client.post(url, json=body, headers=h)
    assert replay.json()["data"] == done.json()["data"]
    closed = await action(a, done, "finish")
    assert closed[0].status_code == 409
    r, _, _ = await start(context)
    abandoned, _, _, _ = await action(a, r, "abandon")
    assert abandoned.status_code == 200 and abandoned.json()["data"]["status"] == "abandoned"
    assert "result" not in abandoned.json()["data"]
    noresult = await a.client.get("/api/v1/attempts/" + r.json()["data"]["id"] + "/result")
    assert noresult.status_code == 409
    assert (await a.client.get("/api/v1/me/active-attempt")).json()["data"] is None


async def test_stale_version_old_item_missing_headers_and_active_start(context):
    a, _, _ = context
    r, _, _ = await start(context)
    active = await a.client.post(
        "/api/v1/attempts",
        json={"topic_id": r.json()["data"]["topic_id"]},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert active.status_code == 409 and active.json()["error"]["code"] == "ACTIVE_ATTEMPT_EXISTS"
    moved, _, _, _ = await action(a, r, "skip")
    stale = await action(a, r, "skip")
    assert (
        stale[0].status_code == 409
        and stale[0].json()["error"]["code"] == "ATTEMPT_VERSION_CONFLICT"
    )
    olditem = await action(a, moved, "advance", {"item_id": r.json()["data"]["current_item"]["id"]})
    assert (
        olditem[0].status_code == 409
        and olditem[0].json()["error"]["code"] == "CURRENT_ITEM_REQUIRED"
    )
    missing = await a.client.post(
        f"/api/v1/attempts/{r.json()['data']['id']}/finish",
        json={},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert missing.status_code == 412


async def test_withdraw_and_new_revision_do_not_change_started_snapshot(context):
    a, sessions, data = context
    r, _, _ = await start(context)
    original = r.json()["data"]["current_item"]
    async with sessions.begin() as db:
        old = await db.get(QuestionRevision, data["revisions"][0].id)
        old.status = "withdrawn"
        await db.flush()
        new = QuestionRevision(
            id=uuid4(),
            question_id=old.question_id,
            revision_number=2,
            text="NEW PUBLISHED TEXT",
            explanation="NEW EXPLANATION",
            fingerprint="a" * 64,
        )
        db.add(new)
        await db.flush()
        db.add_all(
            [
                QuestionOption(
                    id=uuid4(),
                    revision_id=new.id,
                    code=chr(65 + i),
                    position=i,
                    text="NEW OPTION " + str(i),
                    is_correct=i == 1,
                )
                for i in range(2)
            ]
        )
        await db.flush()
        new.status = "published"
        await db.flush()
        q = await db.get(Question, old.question_id)
        q.current_revision_id = new.id
    resumed = await a.client.get("/api/v1/attempts/" + r.json()["data"]["id"])
    assert resumed.json()["data"]["current_item"] == original
    submitted, _, _, _ = await action(
        a, resumed, "submit", {"selected_option_ids": [original["options"][0]["id"]]}
    )
    assert (
        submitted.status_code == 200
        and submitted.json()["data"]["current_item"]["feedback"]["is_correct"] is True
    )
    assert (
        submitted.json()["data"]["current_item"]["feedback"]["explanation"] == "SECRET-EXPLANATION"
    )


@pytest.mark.parametrize("correct,expected", [(0, 0), (1, 13), (7, 88), (8, 100)])
async def test_server_round_half_up_and_full_completion(context, correct, expected):
    a, sessions, data = context
    async with sessions.begin() as db:
        for i in range(6):
            q = Question(id=uuid4(), external_source="synthetic-learning", external_id=uuid4().hex)
            db.add(q)
            await db.flush()
            rev = QuestionRevision(
                id=uuid4(),
                question_id=q.id,
                revision_number=1,
                text=f"SYNTHETIC {i}",
                fingerprint="b" * 64,
            )
            db.add(rev)
            await db.flush()
            db.add_all(
                [
                    QuestionOption(
                        id=uuid4(),
                        revision_id=rev.id,
                        code=chr(65 + j),
                        position=j,
                        text="OPTION " + str(j),
                        is_correct=j == 0,
                    )
                    for j in range(2)
                ]
            )
            await db.flush()
            rev.status = "published"
            await db.flush()
            q.current_revision_id = rev.id
            db.add(TopicQuestion(topic_id=data["topic"].id, question_id=q.id, position=i + 3))
            await db.flush()
    r, _, _ = await start(context)
    assert r.json()["data"]["total"] == 8
    for i in range(8):
        item = r.json()["data"]["current_item"]
        r, _, _, _ = await action(
            a,
            r,
            "submit",
            {"selected_option_ids": [item["options"][0 if i < correct else 1]["id"]]},
        )
        assert r.status_code == 200, r.text
        r, _, _, _ = await action(a, r, "advance")
        assert r.status_code == 200, r.text
    final = r.json()["data"]["result"]
    assert (final["correct"], final["wrong"], final["skipped"], final["percent"]) == (
        correct,
        8 - correct,
        0,
        expected,
    )


async def test_owner_csrf_and_no_unsupported_mode_or_forged_result(context, admin_clients):
    a, _, _ = context
    r, _, _ = await start(context)
    aid = r.json()["data"]["id"]
    async with admin_clients("admin") as other:
        other.app.state.database.sessions = context[1]
        assert (await other.client.get("/api/v1/attempts/" + aid)).status_code == 404
        assert (await other.client.get("/api/v1/attempts/" + aid + "/result")).status_code == 404
        assert (
            await other.client.post(
                "/api/v1/attempts/" + aid + "/finish",
                json={},
                headers={
                    **other.headers,
                    "If-Match": r.headers["etag"],
                    "Idempotency-Key": str(uuid4()),
                },
            )
        ).status_code == 404
    missing = await a.client.post(
        "/api/v1/attempts/" + aid + "/finish",
        json={},
        headers={
            "Origin": a.headers["Origin"],
            "If-Match": r.headers["etag"],
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert missing.status_code == 403
    for body in (
        {"mode": "unsupported", "topic_id": r.json()["data"]["topic_id"]},
        {"discipline_id": r.json()["data"]["discipline_id"], "correct": 99},
    ):
        assert (
            await a.client.post(
                "/api/v1/attempts",
                json=body,
                headers={**a.headers, "Idempotency-Key": str(uuid4())},
            )
        ).status_code == 422
    fake = await action(a, r, "finish", {"duration_seconds": 999, "percent": 100})
    assert fake[0].status_code == 422


async def test_db_guards_snapshot_responses_receipts_and_final_result(context):
    from sqlalchemy.exc import DBAPIError

    a, sessions, _ = context
    r, _, _ = await start(context)
    item = r.json()["data"]["current_item"]
    r, _, _, _ = await action(a, r, "submit", {"selected_option_ids": [item["options"][0]["id"]]})
    assert r.status_code == 200, r.text
    async with sessions.begin() as db:
        for statement in (
            update(AttemptItem).values(position=99),
            update(AttemptOption).values(position=7),
            update(AttemptResponse).values(is_correct=False),
            update(AttemptCommand).values(result={}),
            text("TRUNCATE attempt_commands"),
        ):
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(statement)
    done, _, _, _ = await action(a, r, "finish")
    assert done.status_code == 200, done.text
    async with sessions.begin() as db:
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    update(Attempt)
                    .where(Attempt.id == UUID(done.json()["data"]["id"]))
                    .values(percent=99)
                )


async def test_start_and_submit_replay_survive_generic_idempotency_ttl(context):
    from datetime import UTC, datetime, timedelta

    a, sessions, _ = context
    r, body, headers = await start(context)
    item = r.json()["data"]["current_item"]
    submitted, url, payload, h = await action(
        a, r, "submit", {"selected_option_ids": [item["options"][0]["id"]]}
    )
    advanced, advance_url, advance_body, advance_headers = await action(a, submitted, "advance")
    next_item = advanced.json()["data"]["current_item"]
    checked, _, _, _ = await action(
        a, advanced, "submit", {"selected_option_ids": [next_item["options"][1]["id"]]}
    )
    await action(a, checked, "finish")
    async with sessions.begin() as db:
        await db.execute(
            update(IdempotencyRequest)
            .where(IdempotencyRequest.actor_id == a.user_id)
            .values(
                created_at=datetime.now(UTC) - timedelta(days=9),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    replay = await a.client.post("/api/v1/attempts", json=body, headers=headers)
    assert replay.status_code == 201 and replay.json()["data"] == r.json()["data"]
    replay = await a.client.post(url, json=payload, headers=h)
    assert replay.status_code == 200 and replay.json()["data"] == submitted.json()["data"]
    replay = await a.client.post(advance_url, json=advance_body, headers=advance_headers)
    assert replay.status_code == 200 and replay.json()["data"] == advanced.json()["data"]
    assert "feedback" not in replay.text


async def test_failure_after_response_flush_rolls_back_and_allows_same_key_retry(
    context, monkeypatch
):
    from app.attempts import service

    a, sessions, _ = context
    r, _, _ = await start(context)
    item = r.json()["data"]["current_item"]
    key = str(uuid4())
    original = service.view

    async def failure(*args):
        raise RuntimeError("SYNTHETIC NETWORK BEFORE COMMIT")

    monkeypatch.setattr(service, "view", failure)
    failed, _, _, _ = await action(
        a, r, "submit", {"selected_option_ids": [item["options"][0]["id"]]}, key=key
    )
    monkeypatch.setattr(service, "view", original)
    async with sessions() as db:
        assert await db.get(AttemptResponse, UUID(item["id"])) is None
        assert (await db.get(Attempt, UUID(r.json()["data"]["id"]))).version == 1
    retry, _, _, _ = await action(
        a, r, "submit", {"selected_option_ids": [item["options"][0]["id"]]}, key=key
    )
    assert retry.status_code == 200 and retry.json()["data"]["version"] == 2, retry.text


async def test_unavailable_empty_and_unsupported_definition(context):
    from app.content.models import AccessPolicy, TestDefinition, Topic

    a, sessions, data = context
    async with sessions.begin() as db:
        empty = Topic(
            id=uuid4(),
            discipline_id=data["d"].id,
            slug=uuid4().hex,
            title="EMPTY",
            status="published",
        )
        db.add(empty)
    response = await a.client.post(
        "/api/v1/attempts",
        json={"topic_id": str(empty.id)},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "EMPTY_QUESTION_SET"
    async with sessions.begin() as db:
        definition = await db.get(TestDefinition, data["definition"].id)
        definition.question_limit = 1
    response = await a.client.post(
        "/api/v1/attempts",
        json={"test_definition_id": str(data["definition"].id)},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert (
        response.status_code == 422 and response.json()["error"]["code"] == "UNSUPPORTED_SELECTION"
    )
    async with sessions.begin() as db:
        policy = AccessPolicy(
            id=uuid4(), code=uuid4().hex, requirement="unavailable", status="published"
        )
        db.add(policy)
        await db.flush()
        topic = await db.get(Topic, data["topic"].id)
        topic.access_policy_id = policy.id
    response = await a.client.post(
        "/api/v1/attempts",
        json={"topic_id": str(data["topic"].id)},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 404


async def test_learning_history_blocks_destructive_downgrade(context):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    await start(context)
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0008_learning_attempts.py"
    spec = importlib.util.spec_from_file_location("learning_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def down(conn):
        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()

    async with context[1].begin() as db:
        conn = await db.connection()
        with pytest.raises(RuntimeError, match="learning history exists"):
            await conn.run_sync(down)


async def test_response_requires_version_increment_and_server_correctness(context):
    from sqlalchemy.exc import DBAPIError

    a, sessions, _ = context
    r, _, _ = await start(context)
    item = r.json()["data"]["current_item"]
    async with sessions.begin() as db:
        for correct in (False, True):
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    db.add(
                        AttemptResponse(
                            item_id=UUID(item["id"]),
                            attempt_id=UUID(r.json()["data"]["id"]),
                            revision_id=UUID(item["revision_id"]),
                            state="committed",
                            selected_option_id=UUID(item["options"][0]["id"]),
                            is_correct=correct,
                        )
                    )
                    await db.flush()
                    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_finish_large_snapshot_marks_unvisited_as_skipped(context):
    a, sessions, data = context
    async with sessions.begin() as db:
        questions = [
            Question(
                id=uuid4(), external_source="synthetic-learning-large", external_id=uuid4().hex
            )
            for _ in range(498)
        ]
        db.add_all(questions)
        await db.flush()
        revisions = [
            QuestionRevision(
                id=uuid4(),
                question_id=q.id,
                revision_number=1,
                text="SYNTHETIC BULK QUESTION",
                fingerprint="d" * 64,
            )
            for q in questions
        ]
        db.add_all(revisions)
        await db.flush()
        db.add_all(
            [
                QuestionOption(
                    id=uuid4(),
                    revision_id=r.id,
                    code=chr(65 + j),
                    position=j,
                    text="OPTION " + str(j),
                    is_correct=j == 0,
                )
                for r in revisions
                for j in range(2)
            ]
        )
        await db.flush()
        for i, (q, r) in enumerate(zip(questions, revisions, strict=True)):
            r.status = "published"
            q.current_revision_id = r.id
            db.add(TopicQuestion(topic_id=data["topic"].id, question_id=q.id, position=i + 3))
        await db.flush()
    r, _, _ = await start(context)
    assert r.json()["data"]["total"] == 500
    done, _, _, _ = await action(a, r, "finish")
    assert done.status_code == 200, done.text
    assert done.json()["data"]["result"]["skipped"] == 500
    assert done.json()["data"]["result"]["percent"] == 0
    async with sessions.begin() as db:
        await db.execute(
            text("SET CONSTRAINTS attempt_consistency, attempt_response_consistency IMMEDIATE")
        )


async def test_discipline_snapshot_deduplicates_questions_across_topics(context):
    from app.content.models import Topic

    a, sessions, data = context
    async with sessions.begin() as db:
        topic = Topic(
            id=uuid4(),
            discipline_id=data["d"].id,
            slug=uuid4().hex,
            title="SECOND TOPIC",
            position=1,
            status="published",
        )
        db.add(topic)
        await db.flush()
        db.add(TopicQuestion(topic_id=topic.id, question_id=data["questions"][0].id, position=0))
    r, _, _ = await start(context, "discipline")
    assert r.json()["data"]["total"] == 2
