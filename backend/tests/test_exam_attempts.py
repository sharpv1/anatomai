"""Exam HTTP contract on PostgreSQL: no answer keys before immutable finalization."""
# ruff: noqa: F811 -- imported pytest transaction fixture

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from test_learning_attempts import context  # noqa: F401 -- shared isolated transaction fixture

from app.attempts.models import AttemptResponse
from app.content.models import Question, QuestionRevision
from app.content.models import TestDefinition as Definition
from app.db.models import IdempotencyRequest

pytestmark = pytest.mark.integration


async def start_exam(c, scope="topic", count=None, seconds=None):
    a, sessions, data = c
    if seconds is not None:
        async with sessions.begin() as db:
            await db.execute(
                update(Definition)
                .where(Definition.id == data["definition"].id)
                .values(exam_duration_seconds=seconds)
            )
        scope = "test"
    body = {
        "mode": "exam",
        {"topic": "topic_id", "test": "test_definition_id", "discipline": "discipline_id"}[
            scope
        ]: str(data[{"topic": "topic", "test": "definition", "discipline": "d"}[scope]].id),
    }
    if count is not None:
        body["question_count"] = count
    h = {**a.headers, "Idempotency-Key": str(uuid4())}
    r = await a.client.post("/api/v1/attempts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r, body, h


async def cmd(a, r, op, body=None, item=None, key=None):
    d = r.json()["data"]
    item = item or (d["current_item"]["id"] if d["current_item"] else None)
    url = f"/api/v1/attempts/{d['id']}/" + (f"items/{item}/draft" if op == "draft" else op)
    h = {**a.headers, "If-Match": r.headers["etag"], "Idempotency-Key": key or str(uuid4())}
    call = a.client.put if op == "draft" else a.client.post
    response = await call(url, json=body or {}, headers=h)
    return response, url, h


def safe(r):
    assert r.status_code in (200, 201), r.text
    for field in ("is_correct", "correct_option_ids", "explanation", "feedback", "percent"):
        assert field not in r.text


@pytest.mark.parametrize("scope", ["topic", "discipline", "test"])
async def test_exam_scopes_count_and_timer(context, scope):
    r, _, _ = await start_exam(context, scope, count=1)
    safe(r)
    d = r.json()["data"]
    assert d["total"] == 1 and d["mode"] == "exam"
    assert 0 < d["remaining_seconds"] <= 90 if scope == "test" else d["remaining_seconds"] <= 60
    a, _, _ = context
    resumed = await a.client.get("/api/v1/attempts/" + d["id"])
    safe(resumed)
    assert resumed.json()["data"]["deadline_at"] == d["deadline_at"]


async def test_drafts_edit_clear_navigate_finish_and_review(context):
    a, sessions, _ = context
    r, _, _ = await start_exam(context)
    first = r.json()["data"]["current_item"]
    aid = r.json()["data"]["id"]
    assert (await a.client.get(f"/api/v1/attempts/{aid}/review")).status_code == 409
    forbidden = await a.client.post(
        f"/api/v1/attempts/{aid}/items/{first['id']}/submit",
        json={"selected_option_ids": [first["options"][0]["id"]]},
        headers={**a.headers, "If-Match": r.headers["etag"], "Idempotency-Key": str(uuid4())},
    )
    assert forbidden.status_code == 422
    saved, url, h = await cmd(a, r, "draft", {"selected_option_ids": [first["options"][1]["id"]]})
    safe(saved)
    replay = await a.client.put(
        url, json={"selected_option_ids": [first["options"][1]["id"]]}, headers=h
    )
    assert replay.json()["data"] == saved.json()["data"]
    r, _, _ = await cmd(a, saved, "navigate", {"position": 1})
    safe(r)
    second = r.json()["data"]["current_item"]
    r, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [second["options"][0]["id"]]})
    safe(r)
    r, _, _ = await cmd(a, r, "navigate", {"position": 0})
    safe(r)
    assert r.json()["data"]["current_item"]["selected_option_ids"] == [first["options"][1]["id"]]
    r, _, _ = await cmd(a, r, "draft", {"selected_option_ids": []})
    safe(r)
    assert r.json()["data"]["current_item"]["selected_option_ids"] == []
    r, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [first["options"][0]["id"]]})
    safe(r)
    done, url, h = await cmd(a, r, "finish")
    assert done.status_code == 200, done.text
    result = done.json()["data"]["result"]
    assert (result["correct"], result["wrong"], result["skipped"], result["percent"]) == (
        2,
        0,
        0,
        100,
    )
    review = await a.client.get(f"/api/v1/attempts/{aid}/review?limit=1")
    assert review.status_code == 200 and review.json()["data"]["next_offset"] == 1
    assert review.json()["data"]["items"][0]["correct_option_ids"] == [first["options"][0]["id"]]
    assert review.json()["data"]["items"][0]["explanation"] == "SECRET-EXPLANATION"
    assert (await cmd(a, done, "draft", {"selected_option_ids": []}, item=first["id"]))[
        0
    ].status_code == 409
    assert (await a.client.post(url, json={}, headers=h)).json()["data"] == done.json()["data"]
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AttemptResponse)
                .where(AttemptResponse.attempt_id == UUID(aid))
            )
            == 2
        )


@pytest.mark.parametrize(
    "resume_path", ["/attempts/{id}", "/me/active-attempt", "/attempts/{id}/result"]
)
async def test_timeout_resume_and_late_draft(context, resume_path):
    a, _, _ = context
    r, _, _ = await start_exam(context, seconds=1)
    aid = r.json()["data"]["id"]
    item = r.json()["data"]["current_item"]
    saved, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
    safe(saved)
    await asyncio.sleep(1.08)
    resumed = await a.client.get("/api/v1" + resume_path.format(id=aid))
    assert resumed.status_code == 200, resumed.text
    d = resumed.json()["data"]
    result = d.get("result", d)
    assert (
        result["finish_reason"] == "timeout" and result["correct"] == 1 and result["skipped"] == 1
    )
    assert result["duration_seconds"] in (
        0,
        1,
    )  # database-owned timestamps; see exact duration assertion below
    closed = await a.client.get(f"/api/v1/attempts/{aid}")
    assert closed.json()["data"]["remaining_seconds"] == 0
    assert closed.json()["data"]["result"]["finalized_at"] == r.json()["data"]["deadline_at"]


async def test_expired_command_commits_timeout_and_reference_lock(context):
    a, _, data = context
    r, _, _ = await start_exam(context, seconds=1)
    ref = f"/api/v1/topics/{data['topic'].id}/reference-questions"
    assert (await a.client.get(ref)).status_code == 409
    assert (
        await a.client.get(
            f"/api/v1/test-definitions/{data['definition'].id}/questions?projection=learning"
        )
    ).status_code == 409
    await asyncio.sleep(1.08)
    item = r.json()["data"]["current_item"]
    late, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
    assert late.status_code == 200, late.text
    assert late.json()["data"]["result"]["correct"] == 0
    assert late.json()["data"]["result"]["skipped"] == 2
    assert (await a.client.get(ref)).status_code == 200


async def test_original_snapshot_after_withdraw(context):
    a, sessions, data = context
    r, _, _ = await start_exam(context)
    item = r.json()["data"]["current_item"]
    async with sessions.begin() as db:
        await db.execute(
            update(Question)
            .where(Question.id == data["questions"][0].id)
            .values(current_revision_id=None)
        )
        await db.execute(
            update(QuestionRevision)
            .where(QuestionRevision.id == data["revisions"][0].id)
            .values(status="withdrawn")
        )
    r, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
    safe(r)
    done, _, _ = await cmd(a, r, "finish")
    assert done.status_code == 200 and done.json()["data"]["result"]["correct"] == 1, done.text


async def test_replay_after_cache_expiry_preserves_original_draft(context):
    a, sessions, _ = context
    r, _, _ = await start_exam(context)
    item = r.json()["data"]["current_item"]
    body = {"selected_option_ids": [item["options"][0]["id"]]}
    saved, url, h = await cmd(a, r, "draft", body)
    updated, _, _ = await cmd(
        a, saved, "draft", {"selected_option_ids": [item["options"][1]["id"]]}
    )
    async with sessions.begin() as db:
        await db.execute(
            update(IdempotencyRequest).values(
                created_at=func.now() - text("interval '9 days'"),
                expires_at=func.now() - text("interval '8 days'"),
            )
        )
    replay = await a.client.put(url, json=body, headers=h)
    assert replay.status_code == 200 and replay.json()["data"] == saved.json()["data"], replay.text
    resumed = await a.client.get("/api/v1/attempts/" + r.json()["data"]["id"])
    assert resumed.json()["data"]["current_item"] == updated.json()["data"]["current_item"]


async def test_validation_ownership_csrf_and_abandon(context, admin_clients):
    a, _, data = context
    for extra in (
        {"question_count": 3},
        {"question_count": 0},
        {"deadline_at": "2100-01-01"},
        {"duration_seconds": 100},
        {"score": 99},
    ):
        response = await a.client.post(
            "/api/v1/attempts",
            json={"mode": "exam", "topic_id": str(data["topic"].id), **extra},
            headers={**a.headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422, response.text
    r, _, _ = await start_exam(context)
    aid = r.json()["data"]["id"]
    item = r.json()["data"]["current_item"]
    bad, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [str(data["options"][1][0].id)]})
    assert bad.status_code == 422
    assert (await cmd(a, r, "navigate", {"position": 2}))[0].status_code == 422
    async with admin_clients("admin") as other:
        other.app.state.database.sessions = context[1]
        for suffix in ("", "/result", "/review"):
            assert (await other.client.get(f"/api/v1/attempts/{aid}" + suffix)).status_code == 404
    response = await a.client.put(
        f"/api/v1/attempts/{aid}/items/{item['id']}/draft",
        json={"selected_option_ids": []},
        headers={
            "Origin": a.headers["Origin"],
            "If-Match": r.headers["etag"],
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 403
    response = await a.client.put(
        f"/api/v1/attempts/{aid}/items/{item['id']}/draft",
        json={"selected_option_ids": []},
        headers={**a.headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 412
    abandoned, _, _ = await cmd(a, r, "abandon")
    assert abandoned.status_code == 200 and "result" not in abandoned.json()["data"]
    assert (await a.client.get(f"/api/v1/attempts/{aid}/review")).status_code == 409


async def test_deadline_crosses_during_draft_flush(context):
    import time

    from sqlalchemy import event

    from app.attempts.models import ExamAnswer

    a, _, _ = context
    r, _, _ = await start_exam(context, seconds=1)
    item = r.json()["data"]["current_item"]

    def delay(mapper, connection, target):
        time.sleep(1.1)

    event.listen(ExamAnswer, "before_insert", delay)
    try:
        late, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
        assert late.status_code == 200, late.text
        assert late.json()["data"]["result"]["finish_reason"] == "timeout"
        assert late.json()["data"]["result"]["skipped"] == 2
    finally:
        event.remove(ExamAnswer, "before_insert", delay)


async def test_database_rejects_terminal_draft_result_and_snapshot_changes(context):
    from sqlalchemy.exc import DBAPIError

    from app.attempts.models import Attempt, AttemptItem, ExamAnswer

    a, sessions, _ = context
    r, _, _ = await start_exam(context)
    item = r.json()["data"]["current_item"]
    saved, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
    done, _, _ = await cmd(a, saved, "finish")
    assert done.status_code == 200, done.text
    for statement in (
        update(Attempt).where(Attempt.id == UUID(r.json()["data"]["id"])).values(percent=0),
        update(Attempt)
        .where(Attempt.id == UUID(r.json()["data"]["id"]))
        .values(deadline_at=func.now() + text("interval '1 day'")),
        update(ExamAnswer)
        .where(ExamAnswer.item_id == UUID(item["id"]))
        .values(selected_option_id=UUID(item["options"][1]["id"])),
        update(AttemptItem).where(AttemptItem.id == UUID(item["id"])).values(position=1),
    ):
        async with sessions.begin() as db:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(statement)


async def test_exam_skip_advance_and_zero_result(context):
    a, _, _ = context
    r, _, _ = await start_exam(context)
    item = r.json()["data"]["current_item"]
    moved, _, _ = await cmd(a, r, "skip", {"item_id": item["id"]})
    assert moved.status_code == 200 and moved.json()["data"]["current_position"] == 1, moved.text
    safe(moved)
    item = moved.json()["data"]["current_item"]
    done, _, _ = await cmd(a, moved, "advance", {"item_id": item["id"]})
    assert done.status_code == 200, done.text
    assert done.json()["data"]["result"]["percent"] == 0
    assert done.json()["data"]["result"]["skipped"] == 2


async def test_learning_original_start_fingerprint_and_new_operations_rejected(context):
    from test_learning_attempts import start

    from app.attempts.models import AttemptCommand
    from app.core.idempotency import request_fingerprint

    a, sessions, _ = context
    r, body, h = await start(context)
    # The canonical body from 4a has no question_count field at all.
    old_body = {
        "mode": "learning",
        "kind": "regular",
        "discipline_id": None,
        "topic_id": body["topic_id"],
        "test_definition_id": None,
    }
    expected = request_fingerprint(
        {"attempt_id": None, "item_id": None, "if_match": None, "body": old_body}
    )
    async with sessions() as db:
        receipt = await db.scalar(
            select(AttemptCommand).where(AttemptCommand.key == UUID(h["Idempotency-Key"]))
        )
        assert receipt.request_hash == expected
    for op, payload in [("draft", {"selected_option_ids": []}), ("navigate", {"position": 0})]:
        rejected, _, _ = await cmd(a, r, op, payload)
        assert rejected.status_code == 422
    resumed = await a.client.get("/api/v1/attempts/" + r.json()["data"]["id"])
    assert resumed.json()["data"] == r.json()["data"]


async def test_expired_replay_after_completion_does_not_leak_feedback(context):
    a, sessions, _ = context
    r, body, headers = await start_exam(context)
    item = r.json()["data"]["current_item"]
    answer = {"selected_option_ids": [item["options"][0]["id"]]}
    saved, url, h = await cmd(a, r, "draft", answer)
    done, _, _ = await cmd(a, saved, "finish")
    assert done.status_code == 200
    async with sessions.begin() as db:
        await db.execute(
            update(IdempotencyRequest).values(
                created_at=func.now() - text("interval '9 days'"),
                expires_at=func.now() - text("interval '8 days'"),
            )
        )
    oldstart = await a.client.post("/api/v1/attempts", json=body, headers=headers)
    assert oldstart.json()["data"] == r.json()["data"]
    safe(oldstart)
    oldsave = await a.client.put(url, json=answer, headers=h)
    assert oldsave.json()["data"] == saved.json()["data"]
    safe(oldsave)
