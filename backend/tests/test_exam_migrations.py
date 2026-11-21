"""0008 -> 0009 preserves existing Learning state, responses and idempotent receipts."""

# ruff: noqa: F811 -- imported pytest fixture
import asyncio
from uuid import uuid4

import pytest
from alembic import command
from test_learning_concurrency import bank
from test_publishing_concurrency import authenticated, committed_settings  # noqa: F401 -- fixtures

pytestmark = pytest.mark.integration


async def test_upgrade_preserves_learning_answers_and_original_replay(
    committed_settings, monkeypatch, alembic_config
):
    async with authenticated(committed_settings, monkeypatch) as (client, headers, db):
        tid = await bank(db)
        h = {**headers, "Idempotency-Key": str(uuid4())}
        start = await client.post("/api/v1/attempts", json={"topic_id": str(tid)}, headers=h)
        assert start.status_code == 201, start.text
        item = start.json()["data"]["current_item"]
        aid = start.json()["data"]["id"]
        sh = {**headers, "Idempotency-Key": str(uuid4()), "If-Match": start.headers["etag"]}
        body = {"selected_option_ids": [item["options"][0]["id"]]}
        url = f"/api/v1/attempts/{aid}/items/{item['id']}/submit"
        saved = await client.post(url, json=body, headers=sh)
        assert saved.status_code == 200, saved.text
        # 0009 supports rollback with Learning history, but never with Exam history.
        await asyncio.to_thread(command.downgrade, alembic_config, "0008_learning_attempts")
        await asyncio.to_thread(command.upgrade, alembic_config, "head")
        resumed = await client.get(f"/api/v1/attempts/{aid}")
        assert resumed.status_code == 200 and resumed.json()["data"] == saved.json()["data"], (
            resumed.text
        )
        replay = await client.post(url, json=body, headers=sh)
        assert replay.status_code == 200 and replay.json()["data"] == saved.json()["data"]
