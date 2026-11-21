"""Exact fractions, timezone provenance and real achievement thresholds."""

# ruff: noqa: F811 -- imported pytest fixture
from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from test_exam_attempts import cmd, start_exam
from test_learning_attempts import context  # noqa: F401
from test_progress_api import complete_learning, get

from app.attempts.models import AttemptItem, AttemptOption
from app.content.models import Question, QuestionOption, QuestionRevision, Topic, TopicQuestion
from app.identity.models import User
from app.progress.service import day_in_zone

pytestmark = pytest.mark.integration


async def extend_bank(c, count):
    _, sessions, data = c
    async with sessions.begin() as db:
        for i in range(count):
            q = Question(id=uuid4(), external_source="synthetic-progress", external_id=uuid4().hex)
            db.add(q)
            await db.flush()
            rev = QuestionRevision(
                id=uuid4(),
                question_id=q.id,
                revision_number=1,
                text="SYNTHETIC PROGRESS " + str(i),
                fingerprint="a" * 64,
            )
            db.add(rev)
            await db.flush()
            db.add_all(
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
            await db.flush()
            rev.status = "published"
            await db.flush()
            q.current_revision_id = rev.id
            db.add(TopicQuestion(topic_id=data["topic"].id, question_id=q.id, position=i + 3))
            await db.flush()


async def test_average_uses_unrounded_fractions(context):
    a, _, _ = context
    await extend_bank(context, 4)
    for count in (6, 2):
        r, _, _ = await start_exam(context, count=count)
        item = r.json()["data"]["current_item"]
        saved, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [item["options"][0]["id"]]})
        done, _, _ = await cmd(a, saved, "finish")
        assert done.status_code == 200, done.text
    s = await get(a, "/me/statistics")
    assert s["completed_tests"] == 2 and s["average_percent"] == 33
    assert (await get(a, "/me/progress/topics"))[0]["average_percent"] == 33


async def test_hundred_perfect_from_completed_answers(context):
    a, sessions, _ = context
    await extend_bank(context, 98)
    r, _, _ = await start_exam(context)
    aid = UUID(r.json()["data"]["id"])
    async with sessions() as db:
        choices = (
            await db.execute(
                select(AttemptItem.id, QuestionOption.id)
                .join(AttemptOption, AttemptOption.item_id == AttemptItem.id)
                .join(QuestionOption, QuestionOption.id == AttemptOption.option_id)
                .where(AttemptItem.attempt_id == aid, QuestionOption.is_correct.is_(True))
                .order_by(AttemptItem.position)
            )
        ).all()
    assert len(choices) == 100
    for item, choice in choices:
        r, _, _ = await cmd(a, r, "draft", {"selected_option_ids": [str(choice)]}, item=str(item))
        assert r.status_code == 200, r.text
    assert (await get(a, "/me/statistics"))["answered_count"] == 0
    r, _, _ = await cmd(a, r, "finish")
    assert r.status_code == 200, r.text
    achievements = {x["code"]: x for x in await get(a, "/me/achievements")}
    assert all(achievements[c]["state"] == "unlocked" for c in ("first", "hundred", "perfect"))
    assert achievements["three"]["state"] == "locked"
    assert (await get(a, "/me/statistics"))["correct_count"] == 100


async def test_timezone_change_keeps_calendar_date(context):
    a, sessions, _ = context
    async with sessions.begin() as db:
        await db.execute(
            update(User).where(User.id == a.user_id).values(timezone="Pacific/Kiritimati")
        )
    done = await complete_learning(context, True)
    final = datetime.fromisoformat(done.json()["data"]["result"]["finalized_at"])
    expected = day_in_zone(final, "Pacific/Kiritimati").isoformat()
    async with sessions.begin() as db:
        await db.execute(
            update(User).where(User.id == a.user_id).values(timezone="Pacific/Honolulu")
        )
    history = await get(a, "/me/attempts")
    assert history[0]["activity_date"] == expected
    assert history[0]["activity_timezone"] == "Pacific/Kiritimati"
    activity = await get(a, f"/me/calendar?start={expected}&end={expected}")
    assert activity["timezone"] == "Pacific/Honolulu"
    assert activity["days"][0]["completed_tests"] == 1
    assert await get(a, f"/me/result-trends?start={expected}&end={expected}") == activity


async def test_daily_empty_stays_empty_same_day(context):
    a, sessions, data = context
    async with sessions.begin() as db:
        await db.execute(update(Topic).values(status="draft"))
    empty = await get(a, "/me/daily-topic")
    assert empty["topic_id"] is None and empty["availability"] == "empty"
    async with sessions.begin() as db:
        await db.execute(
            update(Topic).where(Topic.id == data["topic"].id).values(status="published")
        )
    assert await get(a, "/me/daily-topic") == empty


async def test_pg_timezone_and_streak_islands(context, monkeypatch):
    import app.progress.service as service

    a, sessions, _ = context
    async with sessions() as db:
        for stamp, zone in [
            ("2026-03-08T07:00:00+00:00", "America/New_York"),
            ("2026-11-01T06:30:00+00:00", "America/New_York"),
            ("2026-11-21T23:59:59+00:00", "Asia/Bishkek"),
        ]:
            actual = await db.scalar(
                text("SELECT (CAST(:stamp AS timestamptz) AT TIME ZONE :zone)::date"),
                {"stamp": datetime.fromisoformat(stamp), "zone": zone},
            )
            assert actual == day_in_zone(datetime.fromisoformat(stamp), zone)
        monkeypatch.setattr(
            service,
            "BASE",
            "WITH completed AS (SELECT d::date AS activity_date FROM "
            "(VALUES ('2026-11-01'),('2026-11-18'),('2026-11-19'),"
            "('2026-11-20'),('2026-11-20')) t(d)), chosen AS (SELECT * FROM completed) ",
        )
        request = SimpleNamespace(
            state=SimpleNamespace(
                identity_db=db,
                identity=SimpleNamespace(user=SimpleNamespace(id=a.user_id, progress_epoch=0)),
            )
        )
        assert await service.streaks(request, date(2026, 11, 21)) == (3, 3)
        assert await service.streaks(request, date(2026, 11, 22)) == (0, 3)
