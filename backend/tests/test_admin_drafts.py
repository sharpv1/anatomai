import asyncio
from uuid import UUID, uuid4

import pytest
from admin_helpers import question, source
from sqlalchemy import func, select

from app.content.models import ContentSource, Discipline, Question, QuestionRevision
from app.identity.models import AuditEvent

pytestmark = pytest.mark.integration


async def create_question(actor, body):
    response = await actor.client.post(
        "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
    )
    assert response.status_code == 201, response.text
    return response


async def test_all_admin_routes_require_mfa_and_no_client_header_can_assert_it(admin_clients):
    async with admin_clients(confirmed=False) as actor:
        for path in ("disciplines", "topics", "test-definitions", "sources", "questions"):
            response = await actor.client.get(
                "/api/v1/admin/" + path, headers={"X-MFA-Verified": "true"}
            )
            assert (
                response.status_code == 403 and response.json()["error"]["code"] == "MFA_REQUIRED"
            )
        for route in actor.app.routes:
            if getattr(route, "path", "").startswith("/api/v1/admin/"):
                assert getattr(route.endpoint, "medexa_permission", None) in {
                    "admin.step_up",
                    "content.admin.read",
                    "content.draft.write",
                }


async def test_draft_catalog_crud_full_replacement_and_soft_archive(admin_clients, database):
    async with admin_clients() as actor:
        discipline = {
            "slug": uuid4().hex,
            "title": "SYNTHETIC DISCIPLINE",
            "icon_key": "test",
            "color_token": "blue",
            "position": 0,
        }
        r = await actor.client.post(
            "/api/v1/admin/disciplines", json=discipline, headers=await actor.write_headers()
        )
        assert r.status_code == 201, r.text
        d_id = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "draft"
        topic = {
            "discipline_id": d_id,
            "slug": uuid4().hex,
            "title": "SYNTHETIC TOPIC",
            "position": 0,
        }
        r = await actor.client.post(
            "/api/v1/admin/topics", json=topic, headers=await actor.write_headers()
        )
        assert r.status_code == 201, r.text
        t_id = r.json()["data"]["id"]
        definition = {
            "topic_id": t_id,
            "slug": uuid4().hex,
            "title": "SYNTHETIC TEST",
            "exam_duration_seconds": 600,
        }
        r = await actor.client.post(
            "/api/v1/admin/test-definitions", json=definition, headers=await actor.write_headers()
        )
        assert r.status_code == 201, r.text
        for kind, entity_id, body in (
            ("test-definitions", r.json()["data"]["id"], definition),
            ("topics", t_id, topic),
            ("disciplines", d_id, discipline),
        ):
            uri = "/api/v1/admin/" + kind + "/" + entity_id
            old = await actor.client.get(uri)
            assert old.status_code == 200 and "etag" in old.headers
            body["title"] += " UPDATED"
            updated = await actor.client.patch(
                uri, json=body, headers={**actor.headers, "If-Match": old.headers["etag"]}
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["data"]["title"] == body["title"]
            archived = await actor.client.delete(uri, headers=await actor.write_headers())
            assert archived.status_code == 200 and archived.json()["data"]["status"] == "withdrawn"
        async with database.sessions() as db:
            assert (await db.get(Discipline, UUID(d_id))).status == "withdrawn"
        assert (await actor.client.get("/api/v1/disciplines/" + d_id)).status_code == 404


async def test_question_edit_resets_review_and_never_changes_public_pointer(
    admin_clients, database
):
    async with admin_clients() as actor:
        s = await source(actor)
        body = question(s["id"])
        created = await create_question(actor, body)
        revision = created.json()["data"]
        assert revision["status"] == "draft" and revision["medical_review_by"] is None
        assert revision["created_by"] == str(actor.user_id)
        old_options = {o["id"] for o in revision["options"]}
        uri = "/api/v1/admin/question-revisions/" + revision["id"]
        body["text"] += " UPDATED"
        edited = await actor.client.patch(uri, json=body, headers=await actor.write_headers())
        assert edited.status_code == 200, edited.text
        assert old_options.isdisjoint({o["id"] for o in edited.json()["data"]["options"]})
        listing = await actor.client.get(
            "/api/v1/admin/questions", params={"query": "UPDATED", "limit": 1}
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()["data"][0]["id"] == revision["question_id"]
        revisions = await actor.client.get(
            "/api/v1/admin/questions/" + revision["question_id"] + "/revisions"
        )
        assert revisions.json()["page"]["total"] == 1
        q = await actor.client.get("/api/v1/admin/questions/" + revision["question_id"])
        assert q.json()["data"]["current_revision_id"] is None
        async with database.sessions() as db:
            audits = (
                await db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.actor_id == actor.user_id,
                        AuditEvent.action == "content.revision.saved",
                    )
                )
            ).all()
            assert len(audits) == 2 and all(event.safe_diff == {} for event in audits)


async def test_other_editors_drafts_and_sources_are_not_exposed_but_reviewer_can_read(
    admin_clients,
):
    async with admin_clients() as author:
        s = await source(author)
        body = question(s["id"])
        revision = (await create_question(author, body)).json()["data"]
        uri = "/api/v1/admin/question-revisions/" + revision["id"]
        async with admin_clients() as other:
            for path in (
                uri,
                "/api/v1/admin/sources/" + s["id"],
                "/api/v1/admin/questions/" + revision["question_id"],
            ):
                assert (await other.client.get(path)).status_code == 404
            assert (
                await other.client.patch(uri, json=body, headers=await other.write_headers())
            ).status_code == 404
            assert (
                await other.client.post(
                    "/api/v1/admin/questions", json=body, headers=await other.write_headers()
                )
            ).status_code == 404
            assert (
                await other.client.get("/api/v1/admin/questions", params={"query": body["text"]})
            ).json()["data"] == []
        async with admin_clients("content_reviewer") as reviewer:
            assert (await reviewer.client.get(uri)).status_code == 200
            assert (
                await reviewer.client.patch(uri, json=body, headers=await reviewer.write_headers())
            ).status_code == 403


@pytest.mark.parametrize("attack", ["status", "reviewer", "pointer", "owner"])
async def test_mass_assignment_cannot_claim_review_or_publication(admin_clients, attack):
    async with admin_clients("admin") as actor:
        body = question((await source(actor))["id"])
        key = {
            "status": "status",
            "reviewer": "medical_review_by",
            "pointer": "current_revision_id",
            "owner": "created_by",
        }[attack]
        body[key] = "published" if attack == "status" else str(uuid4())
        response = await actor.client.post(
            "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "failure",
    ["no_correct", "two_correct", "duplicate_code", "too_many", "utf8", "implicit_boolean"],
)
async def test_invalid_question_drafts_are_rejected(admin_clients, failure):
    async with admin_clients() as actor:
        body = question((await source(actor))["id"])
        if failure in ("no_correct", "two_correct"):
            for option in body["options"]:
                option["is_correct"] = failure == "two_correct"
        if failure == "duplicate_code":
            body["options"][1]["code"] = "A"
        if failure == "too_many":
            body["options"] = body["options"] * 5
        if failure == "utf8":
            body["text"] = "я" * 4001
        if failure == "implicit_boolean":
            body["options"][0]["is_correct"] = "yes"
        response = await actor.client.post(
            "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
        )
        assert response.status_code == 422


async def test_if_match_and_parallel_conflict_prevent_lost_updates(admin_clients):
    async with admin_clients() as actor:
        s = await source(actor)
        uri = "/api/v1/admin/sources/" + s["id"]
        body = {k: s[k] for k in ("slug", "title", "attribution", "license_reference")}
        assert (await actor.client.patch(uri, json=body, headers=actor.headers)).status_code == 412
        headers = await actor.write_headers()
        results = await asyncio.gather(
            *[
                actor.client.patch(uri, json={**body, "title": "CHANGE " + str(i)}, headers=headers)
                for i in range(2)
            ]
        )
        assert sorted(r.status_code for r in results) == [200, 412]


async def test_duplicate_external_key_rolls_back_whole_write_and_audit(admin_clients, database):
    async with admin_clients() as actor:
        body = question((await source(actor))["id"])
        body["external_id"] = uuid4().hex
        await create_question(actor, body)
        async with database.sessions() as db:
            before = await db.scalar(select(func.count()).select_from(QuestionRevision))
        response = await actor.client.post(
            "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
        )
        assert (
            response.status_code == 409 and response.json()["error"]["code"] == "CONTENT_CONFLICT"
        )
        async with database.sessions() as db:
            assert await db.scalar(select(func.count()).select_from(QuestionRevision)) == before
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.actor_id == actor.user_id,
                        AuditEvent.action == "content.revision.saved",
                    )
                )
                == 1
            )


async def test_published_content_cannot_be_mutated_and_proposal_is_a_new_revision(
    admin_clients, content_data, database
):
    async with admin_clients() as actor:
        d = content_data
        revision_id = str(d["revisions"][0].id)
        qid = str(d["questions"][0].id)
        body = question(str(d["source"].id))
        assert (
            await actor.client.patch(
                "/api/v1/admin/question-revisions/" + revision_id,
                json=body,
                headers=await actor.write_headers(),
            )
        ).status_code == 409
        r = await actor.client.post(
            "/api/v1/admin/questions/" + qid + "/revisions",
            json=body,
            headers=await actor.write_headers(),
        )
        assert r.status_code == 201 and r.json()["data"]["revision_number"] == 2, r.text
        assert r.json()["data"]["status"] == "draft"
        uri = "/api/v1/admin/disciplines/" + str(d["d"].id)
        assert (
            await actor.client.delete(uri, headers=await actor.write_headers())
        ).status_code == 409
        async with database.sessions() as db:
            q = await db.get(Question, d["questions"][0].id)
            assert q.current_revision_id == d["revisions"][0].id


async def test_import_review_publish_withdraw_and_roles_remain_closed_even_after_mfa(admin_clients):
    async with admin_clients("admin") as actor:
        for path in (
            "assets",
            "notes",
            "jobs",
            "import-templates/xlsx",
            "auth/enroll",
            "auth/recovery",
            "question-revisions/" + str(uuid4()) + "/publish",
            "question-revisions/" + str(uuid4()) + "/review",
            "question-revisions/" + str(uuid4()) + "/withdraw",
        ):
            assert (
                await actor.client.post("/api/v1/admin/" + path, json={}, headers=actor.headers)
            ).status_code in (404, 405)
        assert (
            await actor.client.put(
                "/api/v1/admin/users/" + str(uuid4()) + "/roles/admin", headers=actor.headers
            )
        ).status_code == 404


async def test_multiple_choice_is_only_a_draft_not_a_published_test(admin_clients):
    async with admin_clients() as actor:
        body = question((await source(actor))["id"])
        body["kind"] = "multiple_choice"
        body["options"][1]["is_correct"] = True
        response = await create_question(actor, body)
        assert response.json()["data"]["kind"] == "multiple_choice"
        assert response.json()["data"]["status"] == "draft"


async def test_source_search_pagination_and_soft_archive(admin_clients, database):
    async with admin_clients() as actor:
        s = await source(actor)
        response = await actor.client.get(
            "/api/v1/admin/sources", params={"query": s["title"], "limit": 1}
        )
        assert response.status_code == 200 and response.json()["page"]["total"] == 1, response.text
        archived = await actor.client.delete(
            "/api/v1/admin/sources/" + s["id"], headers=await actor.write_headers()
        )
        assert archived.status_code == 200 and archived.json()["data"]["status"] == "withdrawn"
        async with database.sessions() as db:
            assert await db.get(ContentSource, UUID(s["id"])) is not None
        body = question(s["id"])
        assert (
            await actor.client.post(
                "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
            )
        ).status_code == 404


async def test_source_legacy_review_metadata_has_no_independent_reviewer_constraint(
    admin_clients, database
):
    async with admin_clients() as actor:
        s = await source(actor)
        async with database.sessions() as db:
            await db.begin()
            try:
                row = await db.get(ContentSource, UUID(s["id"]))
                row.reviewed_by = actor.user_id
                await db.flush()
                assert row.reviewed_by == row.created_by
            finally:
                await db.rollback()
