"""Historical attribution must not follow mutable catalog memberships."""

# ruff: noqa: F811 -- imported fixture
import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, event, select
from test_learning_attempts import action, context, start  # noqa: F401
from test_progress_api import get

from app.attempts.models import AttemptItem
from app.content.models import Topic, TopicQuestion

pytestmark = pytest.mark.integration


async def test_discipline_legacy_unknown_topic_is_explicit(context):
    a, _, _ = context

    def legacy(mapper, connection, target):
        target.topic_id = None

    event.listen(AttemptItem, "before_insert", legacy)
    try:
        r, _, _ = await start(context, "discipline")
    finally:
        event.remove(AttemptItem, "before_insert", legacy)
    done, _, _, _ = await action(a, r, "finish")
    assert done.status_code == 200, done.text
    assert (await get(a, "/me/statistics"))["completed_tests"] == 1
    assert len(await get(a, "/me/progress/disciplines")) == 1
    assert await get(a, "/me/progress/topics") == []
    assert (await get(a, "/me/progress"))["unattributed_topic_responses"] == 2


async def test_new_discipline_topic_snapshot_survives_catalog_move(context):
    a, sessions, data = context
    r, _, _ = await start(context, "discipline")
    aid = UUID(r.json()["data"]["id"])
    async with sessions.begin() as db:
        stored = (await db.scalars(select(AttemptItem).where(AttemptItem.attempt_id == aid))).all()
        assert {i.topic_id for i in stored} == {data["topic"].id}
        new = Topic(
            id=uuid4(),
            discipline_id=data["d"].id,
            slug=uuid4().hex,
            title="SYNTHETIC MOVED TOPIC",
            status="published",
        )
        db.add(new)
        await db.flush()
        await db.execute(delete(TopicQuestion).where(TopicQuestion.topic_id == data["topic"].id))
        db.add_all(
            [
                TopicQuestion(topic_id=new.id, question_id=q.id, position=i)
                for i, q in enumerate(data["questions"])
            ]
        )
    done, _, _, _ = await action(a, r, "finish")
    assert done.status_code == 200, done.text
    topics = await get(a, "/me/progress/topics")
    assert len(topics) == 1 and topics[0]["id"] == str(data["topic"].id)
    assert (await get(a, "/me/progress"))["unattributed_topic_responses"] == 0
    assert len(await get(a, "/me/attempts?topic_id=" + str(data["topic"].id))) == 1
    assert await get(a, "/me/attempts?topic_id=" + str(new.id)) == []


async def test_downgrade_refuses_losing_attribution(context):
    _, sessions, _ = context
    await start(context)
    path = Path(__file__).parents[1] / "migrations/versions/0010_progress_statistics.py"
    spec = importlib.util.spec_from_file_location("progress_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with sessions() as db:
        connection = await db.connection()

        def downgrade(conn):
            with Operations.context(MigrationContext.configure(conn)):
                module.downgrade()

        with pytest.raises(RuntimeError, match="progress attribution"):
            await connection.run_sync(downgrade)
