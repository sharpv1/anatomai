"""Independent PostgreSQL commits, worker races and fresh API instance resume."""
# ruff: noqa: F811 -- imported pytest fixture

import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from test_learning_concurrency import bank
from test_publishing_concurrency import authenticated, committed_settings  # noqa: F401 -- fixtures

from app.attempts.finalizer import run_once
from app.attempts.models import Attempt, AttemptResponse, ExamAnswer
from app.content.models import TestDefinition as Definition
from app.main import create_app

pytestmark = pytest.mark.integration


async def test_exam_concurrent_drafts_replay_restart_finish_timeout(
    committed_settings, monkeypatch
):  # noqa: F811 -- pytest fixture
    settings = committed_settings
    async with authenticated(settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        async with db.sessions.begin() as session:
            definition = Definition(
                id=uuid4(),
                topic_id=tid,
                slug=uuid4().hex,
                title="SYNTHETIC EXAM",
                exam_duration_seconds=3,
                status="published",
            )
            session.add(definition)
        start_h = {**headers, "Idempotency-Key": str(uuid4())}
        body = {"mode": "exam", "test_definition_id": str(definition.id)}
        starts = await asyncio.gather(
            *(client.post("/api/v1/attempts", json=body, headers=start_h) for _ in range(2))
        )
        assert [r.status_code for r in starts] == [201, 201], [r.text for r in starts]
        r = starts[0]
        aid = r.json()["data"]["id"]
        item = r.json()["data"]["current_item"]
        assert starts[1].json()["data"] == r.json()["data"]
        url = f"/api/v1/attempts/{aid}/items/{item['id']}/draft"
        dh = {**headers, "If-Match": r.headers["etag"], "Idempotency-Key": str(uuid4())}
        body = {"selected_option_ids": [item["options"][0]["id"]]}
        saves = await asyncio.gather(*(client.put(url, json=body, headers=dh) for _ in range(2)))
        assert [s.status_code for s in saves] == [200, 200], [s.text for s in saves]
        assert saves[0].json()["data"] == saves[1].json()["data"]
        # A new API factory/pool simulates reopening after a committed response was lost.
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=str(client.base_url),
                cookies=client.cookies,
            ) as fresh:
                replay = await fresh.put(url, json=body, headers=dh)
                assert replay.json()["data"] == saves[0].json()["data"]
                resumed = await fresh.get(f"/api/v1/attempts/{aid}")
                assert (
                    resumed.json()["data"]["current_item"]["selected_option_ids"]
                    == body["selected_option_ids"]
                )
                # Independent requests with different keys, same version: exactly one edit wins.
                races = await asyncio.gather(
                    *(
                        fresh.put(
                            url,
                            json={"selected_option_ids": [o["id"]]},
                            headers={
                                **headers,
                                "If-Match": resumed.headers["etag"],
                                "Idempotency-Key": str(uuid4()),
                            },
                        )
                        for o in item["options"]
                    )
                )
                assert sorted(x.status_code for x in races) == [200, 409], [x.text for x in races]
                latest = next(x for x in races if x.status_code == 200)
                await asyncio.sleep(3.1)
                # Manual completion competes with two independent DB-backed finalizers.
                finish, first_worker, second_worker = await asyncio.gather(
                    fresh.post(
                        f"/api/v1/attempts/{aid}/finish",
                        json={},
                        headers={
                            **headers,
                            "If-Match": latest.headers["etag"],
                            "Idempotency-Key": str(uuid4()),
                        },
                    ),
                    run_once(db),
                    run_once(db),
                )
                assert finish.status_code in (200, 409), finish.text
                final = await fresh.get(f"/api/v1/attempts/{aid}")
                assert (
                    final.status_code == 200
                    and final.json()["data"]["result"]["finish_reason"] == "timeout"
                ), final.text
                result = final.json()["data"]["result"]
                assert (
                    result["answered"] == 1
                    and result["skipped"] == 1
                    and result["duration_seconds"] == 3
                )
                review = await fresh.get(f"/api/v1/attempts/{aid}/review")
                assert review.status_code == 200 and "correct_option_ids" in review.text
        async with db.sessions() as session:
            stored = await session.get(Attempt, UUID(aid))
            assert stored.version == 4
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ExamAnswer)
                    .where(ExamAnswer.attempt_id == UUID(aid))
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AttemptResponse)
                    .where(AttemptResponse.attempt_id == UUID(aid))
                )
                == 2
            )
        assert await run_once(db) is False


async def test_worker_finishes_closed_client_without_http(committed_settings, monkeypatch):  # noqa: F811 -- pytest fixture
    async with authenticated(committed_settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        async with db.sessions.begin() as session:
            definition = Definition(
                id=uuid4(),
                topic_id=tid,
                slug=uuid4().hex,
                title="SYNTHETIC TIMEOUT",
                exam_duration_seconds=1,
                status="published",
            )
            session.add(definition)
        r = await client.post(
            "/api/v1/attempts",
            json={"mode": "exam", "test_definition_id": str(definition.id)},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == 201, r.text
        aid = UUID(r.json()["data"]["id"])
        await asyncio.sleep(1.1)
        assert await run_once(db) is True
        async with db.sessions() as session:
            a = await session.get(Attempt, aid)
            assert (
                a.status == "completed"
                and a.finish_reason == "timeout"
                and a.skipped == 2
                and a.duration_seconds == 1
            )


async def test_finalizer_crash_rolls_back_and_retry_completes(committed_settings, monkeypatch):  # noqa: F811 -- pytest fixture
    import app.attempts.finalizer as worker

    async with authenticated(committed_settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        async with db.sessions.begin() as session:
            definition = Definition(
                id=uuid4(),
                topic_id=tid,
                slug=uuid4().hex,
                title="SYNTHETIC RECOVERY",
                exam_duration_seconds=1,
                status="published",
            )
            session.add(definition)
        r = await client.post(
            "/api/v1/attempts",
            json={"mode": "exam", "test_definition_id": str(definition.id)},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == 201, r.text
        aid = UUID(r.json()["data"]["id"])
        await asyncio.sleep(1.1)
        original = worker.expire

        async def fault(session, attempt):
            await original(session, attempt)
            raise RuntimeError("synthetic crash before commit")

        monkeypatch.setattr(worker, "expire", fault)
        with pytest.raises(RuntimeError, match="synthetic crash"):
            await worker.run_once(db)
        async with db.sessions() as session:
            a = await session.get(Attempt, aid)
            assert a.status == "in_progress" and a.version == 1
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AttemptResponse)
                    .where(AttemptResponse.attempt_id == aid)
                )
                == 0
            )
        monkeypatch.setattr(worker, "expire", original)
        assert await worker.run_once(db) is True
        assert await worker.run_once(db) is False
