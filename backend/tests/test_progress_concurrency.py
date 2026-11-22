"""Computed totals cannot double count replayed or concurrently finalized attempts."""

# ruff: noqa: F811 -- imported pytest fixture
import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from test_learning_concurrency import bank
from test_publishing_concurrency import authenticated, committed_settings  # noqa: F401

from app.attempts.finalizer import run_once
from app.content.models import TestDefinition as Definition
from app.main import create_app

pytestmark = pytest.mark.integration


async def test_finish_replay_timeout_and_restart_have_one_contribution(
    committed_settings, monkeypatch
):
    async with authenticated(committed_settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        r = await client.post(
            "/api/v1/attempts",
            json={"topic_id": str(tid)},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == 201, r.text
        aid = r.json()["data"]["id"]
        h = {**headers, "Idempotency-Key": str(uuid4()), "If-Match": r.headers["etag"]}
        url = f"/api/v1/attempts/{aid}/finish"
        finishes = await asyncio.gather(*(client.post(url, json={}, headers=h) for _ in range(2)))
        assert [x.status_code for x in finishes] == [200, 200]
        for _ in range(3):
            assert (await client.post(url, json={}, headers=h)).status_code == 200
            stats = await client.get("/api/v1/me/statistics")
            assert stats.status_code == 200 and stats.json()["data"]["completed_tests"] == 1
        async with db.sessions.begin() as session:
            definition = Definition(
                id=uuid4(),
                topic_id=tid,
                slug=uuid4().hex,
                title="SYNTHETIC PROGRESS TIMEOUT",
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
        aid = r.json()["data"]["id"]
        await asyncio.sleep(1.1)
        finish, worker, home = await asyncio.gather(
            client.post(
                f"/api/v1/attempts/{aid}/finish",
                json={},
                headers={**headers, "Idempotency-Key": str(uuid4()), "If-Match": r.headers["etag"]},
            ),
            run_once(db),
            client.get("/api/v1/me/home"),
        )
        assert finish.status_code in (200, 409), finish.text
        assert home.status_code == 200, home.text
        assert await run_once(db) is False
        stats = await client.get("/api/v1/me/statistics")
        assert stats.json()["data"]["completed_tests"] == 2
        assert stats.json()["data"]["skipped_count"] == 4
        # Fresh app/pool: no in-memory statistics cache or independent history.
        app = create_app(committed_settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=str(client.base_url),
                cookies=client.cookies,
            ) as fresh:
                result = await fresh.get("/api/v1/me/home")
                assert result.status_code == 200, result.text
                assert result.json()["data"]["statistics"]["completed_tests"] == 2
                assert len(result.json()["data"]["recent_results"]) == 2
                assert result.json()["data"]["active_attempt"] is None
