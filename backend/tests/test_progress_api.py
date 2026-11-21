"""Real PG16 read models fed by authenticated Learning/Exam commands."""

# ruff: noqa: F811 -- reused rollback-only fixture
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from test_exam_attempts import cmd, start_exam
from test_learning_attempts import action, context, start  # noqa: F401 -- pytest fixture

from app.identity.models import User
from app.progress.service import day_in_zone, period_start

pytestmark = pytest.mark.integration


async def get(a, path):
    r = await a.client.get("/api/v1" + path)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def complete_learning(c, answer=None):
    a, _, _ = c
    r, _, _ = await start(c)
    if answer is not None:
        item = r.json()["data"]["current_item"]
        r, _, _, _ = await action(
            a, r, "submit", {"selected_option_ids": [item["options"][0 if answer else 1]["id"]]}
        )
        assert r.status_code == 200, r.text
    done, _, _, _ = await action(a, r, "finish")
    assert done.status_code == 200, done.text
    return done


async def test_empty_statistics_calendar_progress_and_achievements(context):
    a, _, data = context
    stats = await get(a, "/me/statistics")
    assert stats["completed_tests"] == stats["correct_count"] == stats["answered_count"] == 0
    assert stats["average_percent"] is None and stats["practice_seconds"] is None
    assert stats["activity_streak_days"] == 0
    assert await get(a, "/me/attempts") == []
    assert await get(a, "/me/recommendations") == []
    assert (await get(a, "/me/progress"))["unattributed_topic_responses"] == 0
    assert await get(a, "/me/progress/topics") == []
    assert await get(a, "/me/progress/disciplines") == []
    topic = await get(a, f"/me/topics/{data['topic'].id}/summary")
    assert topic["best_percent"] is None and topic["ever_wrong_question_count"] is None
    assert topic["favorites_count"] is None and topic["favorites_status"] == "not_configured"
    activity = await get(a, "/me/activity")
    assert len(activity["days"]) == 7 and sum(d["completed_tests"] for d in activity["days"]) == 0
    achievements = await get(a, "/me/achievements")
    assert len(achievements) == 9 and all(x["state"] != "unlocked" for x in achievements)
    assert sum(x["state"] == "not_configured" for x in achievements) == 5
    home = await get(a, "/me/home")
    assert home["active_attempt"] is None and home["recent_results"] == []


async def test_completed_only_modes_summary_and_safe_review(context):
    a, _, data = context
    # Abandon after a real checked answer must not count.
    r, _, _ = await start(context)
    item = r.json()["data"]["current_item"]
    saved, _, _, _ = await action(
        a, r, "submit", {"selected_option_ids": [item["options"][0]["id"]]}
    )
    abandoned, _, _, _ = await action(a, saved, "abandon")
    assert abandoned.status_code == 200
    assert (await get(a, "/me/statistics"))["completed_tests"] == 0
    done = await complete_learning(context, False)
    learning = done.json()["data"]["id"]
    exam, _, _ = await start_exam(context)
    assert (await get(a, "/me/statistics"))["completed_tests"] == 1
    assert (await get(a, "/me/home"))["active_attempt"]["mode"] == "exam"
    for suffix in ("/result", "/result-review"):
        assert (
            await a.client.get("/api/v1/attempts/" + exam.json()["data"]["id"] + suffix)
        ).status_code == 409
    assert (
        await a.client.get(f"/api/v1/attempts/{learning}/result-review")
    ).status_code == 409  # reference lock
    finished, _, _ = await cmd(a, exam, "finish")
    assert finished.status_code == 200, finished.text
    stats = await get(a, "/me/statistics")
    assert (
        stats["completed_tests"],
        stats["answered_count"],
        stats["correct_count"],
        stats["wrong_count"],
        stats["skipped_count"],
    ) == (2, 1, 0, 1, 3)
    assert stats["average_percent"] == 0 and stats["practice_seconds"] >= 0
    rows = await get(a, "/me/attempts")
    assert len(rows) == 2 and {r["mode"] for r in rows} == {"exam", "learning"}
    assert all("current_item" not in r for r in rows)
    review = await get(a, f"/attempts/{learning}/result-review?selection=all&limit=1")
    assert review["has_more"] is True and review["next_cursor"]
    assert review["items"][0]["is_correct"] is False and "explanation" not in review["items"][0]
    nextpage = await get(
        a,
        f"/attempts/{learning}/result-review?selection=all&limit=1&cursor=" + review["next_cursor"],
    )
    assert nextpage["items"][0]["position"] == 1 and nextpage["items"][0]["is_correct"] is None
    assert len(await get(a, "/me/attempts?mode=learning")) == 1
    home = await get(a, "/me/home")
    assert home["statistics"]["completed_tests"] == 2 and len(home["recent_results"]) == 2


async def test_history_keyset_filters_cursor_owner_and_epoch(context, admin_clients):
    a, sessions, data = context
    ids = []
    for answer in (True, False, None):
        ids.append((await complete_learning(context, answer)).json()["data"]["id"])
    first = await a.client.get("/api/v1/me/attempts?limit=1")
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["data"][0]["id"] == ids[-1]
    cursor = page["page"]["next_cursor"]
    assert cursor
    second = await a.client.get("/api/v1/me/attempts?limit=1&cursor=" + cursor)
    assert second.json()["data"][0]["id"] == ids[-2]
    third = await a.client.get(
        "/api/v1/me/attempts?limit=1&cursor=" + second.json()["page"]["next_cursor"]
    )
    assert third.json()["data"][0]["id"] == ids[-3] and third.json()["page"]["has_more"] is False
    assert (await a.client.get("/api/v1/me/attempts?mode=exam&cursor=" + cursor)).status_code == 400
    assert (
        await a.client.get("/api/v1/me/attempts?cursor=" + cursor[:-2] + "xx")
    ).status_code == 400
    assert len(await get(a, "/me/attempts?topic_id=" + str(data["topic"].id))) == 3
    async with admin_clients("admin") as other:
        other.app.state.database.sessions = sessions
        assert await get(other, "/me/attempts") == []
        assert (await get(other, "/me/statistics"))["completed_tests"] == 0
        assert (await other.client.get("/api/v1/me/attempts?cursor=" + cursor)).status_code == 400
        for suffix in ("/result", "/result-review"):
            assert (
                await other.client.get("/api/v1/attempts/" + ids[0] + suffix)
            ).status_code == 404
    async with sessions.begin() as db:
        await db.execute(update(User).where(User.id == a.user_id).values(progress_epoch=1))
    assert await get(a, "/me/attempts") == []
    assert (await a.client.get("/api/v1/me/attempts?cursor=" + cursor)).status_code == 400
    assert (await get(a, "/me/statistics"))["average_percent"] is None


async def test_error_progress_wrong_then_correct_then_skip(context):
    a, _, data = context
    await complete_learning(context, False)
    t = (await get(a, "/me/progress/topics"))[0]
    assert t["ever_wrong_question_count"] == t["unresolved_wrong_question_count"] == 1
    rec = await get(a, "/me/recommendations")
    assert rec and rec[0]["topic_id"] == str(data["topic"].id)
    await complete_learning(context, True)
    await complete_learning(context)
    t = (await get(a, "/me/progress/topics"))[0]
    assert t["ever_wrong_question_count"] == 1 and t["unresolved_wrong_question_count"] == 0
    assert t["completed_tests"] == 3 and t["observed_questions"] == 2 and t["correct_count"] == 1
    topic = await get(a, f"/me/topics/{data['topic'].id}/summary")
    assert topic["completed_count"] == 3 and topic["best_percent"] == 50
    mistakes = await get(a, "/me/mistakes?group_by=discipline")
    assert mistakes[0]["wrong_count"] == 1 and mistakes[0]["ever_wrong_question_count"] == 1
    activity = await get(a, "/me/activity")
    assert sum(d["completed_tests"] for d in activity["days"]) == 3
    assert (await get(a, "/me/statistics"))["activity_streak_days"] == 1


async def test_daily_stable_withdraw_and_no_silent_replacement(context):
    from app.content.models import Topic

    a, sessions, data = context
    await complete_learning(context, False)
    first = await get(a, "/me/daily-topic")
    assert first["availability"] == "available" and first["question_count"] == 2
    await complete_learning(context, False)
    assert await get(a, "/me/daily-topic") == first
    async with sessions.begin() as db:
        await db.execute(
            update(Topic).where(Topic.id == UUID(first["topic_id"])).values(status="withdrawn")
        )
    changed = await get(a, "/me/daily-topic")
    assert changed["availability"] == "withdrawn" and changed["topic_id"] == first["topic_id"]
    assert changed["title"] is None and changed["question_count"] is None
    assert await get(a, "/me/recommendations") == []


async def test_input_limits_and_no_user_id_override(context):
    a, _, _ = context
    for path in (
        "/me/attempts?limit=101",
        "/me/progress/topics?limit=0",
        "/me/recommendations?limit=11",
        "/me/calendar?start=2020-01-01&end=2025-01-01",
        "/me/calendar?start=2025-01-02&end=2025-01-01",
        "/me/activity?week_start=2026-11-17",
        "/me/attempts?start=2026-11-21&end=2026-11-20",
    ):
        r = await a.client.get("/api/v1" + path)
        assert r.status_code == 422, (path, r.text)
    assert (await get(a, "/me/statistics?user_id=" + str(uuid4())))["completed_tests"] == 0


@pytest.mark.parametrize(
    "stamp,zone,expected",
    [
        ("2026-03-08T06:59:59+00:00", "America/New_York", "2026-03-08"),
        ("2026-03-08T07:00:00+00:00", "America/New_York", "2026-03-08"),
        ("2026-11-01T05:30:00+00:00", "America/New_York", "2026-11-01"),
        ("2026-11-01T06:30:00+00:00", "America/New_York", "2026-11-01"),
        ("2026-11-21T23:59:59+00:00", "Asia/Bishkek", "2026-11-22"),
        ("2026-11-22T00:00:00+00:00", "America/Los_Angeles", "2026-11-21"),
    ],
)
def test_iana_dates_dst_midnight(stamp, zone, expected):
    assert day_in_zone(datetime.fromisoformat(stamp), zone).isoformat() == expected
    assert (
        period_start(datetime(2026, 11, 22, tzinfo=UTC).date(), "week").isoformat() == "2026-11-16"
    )


async def test_history_continues_beyond_first_hundred(context):
    a, _, _ = context
    for _ in range(102):
        await complete_learning(context)
    seen = []
    path = "/api/v1/me/attempts?limit=100"
    while True:
        response = await a.client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        seen.extend(r["id"] for r in data["data"])
        if not data["page"]["has_more"]:
            break
        path = "/api/v1/me/attempts?limit=100&cursor=" + data["page"]["next_cursor"]
    assert len(seen) == len(set(seen)) == 102
    assert (await get(a, "/me/statistics"))["completed_tests"] == 102
