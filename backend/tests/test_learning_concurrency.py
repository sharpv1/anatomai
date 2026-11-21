"""Committed independent transactions and API factory restart, isolated PostgreSQL DB."""

import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from test_publishing_concurrency import authenticated, committed_settings  # noqa: F401 -- fixture reuse

from app.attempts.models import Attempt, AttemptCommand, AttemptResponse
from app.content.models import (
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.main import create_app

pytestmark = pytest.mark.integration


async def bank(db):
    async with db.sessions.begin() as session:
        d = Discipline(
            id=uuid4(),
            slug=uuid4().hex,
            title="SYNTHETIC LEARNING",
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
            title="SYNTHETIC TOPIC",
            status="published",
        )
        session.add(topic)
        await session.flush()
        for i in range(2):
            q = Question(
                id=uuid4(), external_source="synthetic-learning-race", external_id=uuid4().hex
            )
            session.add(q)
            await session.flush()
            rev = QuestionRevision(
                id=uuid4(),
                question_id=q.id,
                revision_number=1,
                text="SYNTHETIC QUESTION " + str(i),
                explanation="SYNTHETIC FEEDBACK",
                fingerprint="c" * 64,
            )
            session.add(rev)
            await session.flush()
            session.add_all(
                [
                    QuestionOption(
                        id=uuid4(),
                        revision_id=rev.id,
                        position=j,
                        code=chr(65 + j),
                        text="OPTION " + str(j),
                        is_correct=j == 0,
                    )
                    for j in range(2)
                ]
            )
            await session.flush()
            rev.status = "published"
            await session.flush()
            q.current_revision_id = rev.id
            session.add(TopicQuestion(topic_id=topic.id, question_id=q.id, position=i))
            await session.flush()
        return topic.id


async def test_concurrent_start_submit_advance_and_api_restart(committed_settings, monkeypatch):  # noqa: F811 -- pytest fixture injection
    settings = committed_settings
    async with authenticated(settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        h = {**headers, "Idempotency-Key": str(uuid4())}
        body = {"topic_id": str(tid)}
        starts = await asyncio.gather(
            *(client.post("/api/v1/attempts", json=body, headers=h) for _ in range(2))
        )
        assert [r.status_code for r in starts] == [201, 201], [r.text for r in starts]
        initial = starts[0]
        a = initial.json()["data"]
        aid = a["id"]
        item = a["current_item"]
        assert starts[1].json()["data"] == a
        different = await client.post(
            "/api/v1/attempts", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
        )
        assert (
            different.status_code == 409
            and different.json()["error"]["code"] == "ACTIVE_ATTEMPT_EXISTS"
        )
        url = f"/api/v1/attempts/{aid}/items/{item['id']}/submit"
        answer = {"selected_option_ids": [item["options"][0]["id"]]}
        sh = {**headers, "If-Match": initial.headers["etag"], "Idempotency-Key": str(uuid4())}
        submits = await asyncio.gather(
            *(client.post(url, json=answer, headers=sh) for _ in range(2))
        )
        assert [r.status_code for r in submits] == [200, 200], [r.text for r in submits]
        assert submits[0].json()["data"] == submits[1].json()["data"]
        # Simulate response loss after commit: a fresh API process only uses durable DB state.
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=str(client.base_url),
                cookies=client.cookies,
            ) as restarted:
                resumed = await restarted.get("/api/v1/attempts/" + aid)
                assert (
                    resumed.status_code == 200
                    and resumed.json()["data"] == submits[0].json()["data"]
                ), resumed.text
                replay = await restarted.post(url, json=answer, headers=sh)
                assert (
                    replay.status_code == 200 and replay.json()["data"] == submits[0].json()["data"]
                )
                ah = {
                    **headers,
                    "If-Match": resumed.headers["etag"],
                    "Idempotency-Key": str(uuid4()),
                }
                advances = await asyncio.gather(
                    *(
                        restarted.post(
                            f"/api/v1/attempts/{aid}/advance",
                            json={"item_id": item["id"]},
                            headers=ah,
                        )
                        for _ in range(2)
                    )
                )
                assert [r.status_code for r in advances] == [200, 200], [r.text for r in advances]
                assert advances[0].json()["data"]["current_position"] == 1
                nextitem = advances[0].json()["data"]["current_item"]
                # Different keys/options with the same version race: exactly one answer commits.
                races = await asyncio.gather(
                    *(
                        restarted.post(
                            f"/api/v1/attempts/{aid}/items/{nextitem['id']}/submit",
                            json={"selected_option_ids": [o["id"]]},
                            headers={
                                **headers,
                                "If-Match": advances[0].headers["etag"],
                                "Idempotency-Key": str(uuid4()),
                            },
                        )
                        for o in nextitem["options"]
                    )
                )
                assert sorted(r.status_code for r in races) == [200, 409], [r.text for r in races]
                checked = next(r for r in races if r.status_code == 200)
                fh = {
                    **headers,
                    "If-Match": checked.headers["etag"],
                    "Idempotency-Key": str(uuid4()),
                }
                finishes = await asyncio.gather(
                    *(
                        restarted.post(f"/api/v1/attempts/{aid}/finish", json={}, headers=fh)
                        for _ in range(2)
                    )
                )
                assert [r.status_code for r in finishes] == [200, 200], [r.text for r in finishes]
                assert finishes[0].json()["data"] == finishes[1].json()["data"]
                result = (await restarted.get(f"/api/v1/attempts/{aid}/result")).json()["data"]
                assert result["correct"] + result["wrong"] + result["skipped"] == 2
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Attempt)) == 1
            assert await session.scalar(select(func.count()).select_from(AttemptResponse)) == 2
            assert await session.scalar(select(func.count()).select_from(AttemptCommand)) == 5
            stored = await session.get(Attempt, UUID(aid))
            assert stored.status == "completed" and stored.version == 5
