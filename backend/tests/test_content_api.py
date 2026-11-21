from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from identity_helpers import ORIGIN, TEST_BOT_TOKEN, TEST_CSRF_KEY, signed_data
from pydantic import SecretStr
from sqlalchemy import select

from app.content.models import (
    Discipline,
    LegacyMapping,
    Note,
    NoteRevision,
    Question,
    QuestionRevision,
)
from app.identity.models import UserRole
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def content_client(database, db_settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    settings = db_settings.model_copy(
        update={
            "telegram_bot_token": SecretStr(TEST_BOT_TOKEN),
            "csrf_signing_key": SecretStr(TEST_CSRF_KEY),
            "content_cursor_signing_key": SecretStr("synthetic-content-cursor-key-" + "c" * 40),
            "app_origin": ORIGIN,
        }
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
            yield client, app, settings


async def authenticate(client):
    r = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_data(uuid4().int % (2**62) + 1)},
        headers={"Origin": ORIGIN},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_legacy_bank_is_quarantined_and_notes_are_empty(content_client, database):
    client, _, _ = content_client
    await authenticate(client)
    async with database.sessions() as db:
        legacy = (
            await db.scalars(
                select(Question).where(Question.external_source == "anatomai-legacy-5450646")
            )
        ).all()
        assert len(legacy) == 10 and all(q.current_revision_id is None for q in legacy)
        revisions = (
            await db.scalars(
                select(QuestionRevision).where(
                    QuestionRevision.question_id.in_([q.id for q in legacy])
                )
            )
        ).all()
        assert len(revisions) == 10 and all(
            r.status == "draft" and r.medical_review_by is None for r in revisions
        )
        mapping = await db.get(LegacyMapping, ("topic", "anatomy"))
        discipline = await db.get(LegacyMapping, ("discipline", "anatomy"))
    assert (await client.get("/api/v1/topics/" + str(mapping.topic_id))).status_code == 404
    assert (
        await client.get("/api/v1/topics/" + str(mapping.topic_id) + "/reference-questions")
    ).status_code == 404
    notes = await client.get(
        "/api/v1/notes", params={"discipline_id": str(discipline.discipline_id)}
    )
    assert (
        notes.status_code == 200
        and notes.json()["data"] == []
        and notes.json()["page"]["total"] == 0
    )


async def test_public_catalog_counts_only_actual_published_available_questions(
    content_client, content_data
):
    client, _, _ = content_client
    data = content_data
    d = await client.get("/api/v1/disciplines/" + str(data["d"].id))
    assert d.status_code == 200 and d.json()["data"]["question_count"] == 2
    assert d.json()["data"]["topic_count"] == 1 and d.json()["data"]["note_count"] == 0
    categories = await client.get("/api/v1/categories", params={"discipline_id": str(data["d"].id)})
    assert categories.json()["data"][0]["id"] == str(data["category"].id)
    topic = await client.get("/api/v1/topics/" + str(data["topic"].id))
    assert topic.json()["data"]["question_count"] == 2
    assert topic.json()["data"]["available_modes"] == []  # no fake attempt engine
    definition = await client.get("/api/v1/test-definitions/" + str(data["definition"].id))
    assert definition.json()["data"]["question_count"] == 2
    assert "internal_difficulty" not in definition.text and "correct" not in definition.text


async def test_reference_requires_identity_and_does_not_expose_explanation(
    content_client, content_data
):
    client, _, _ = content_client
    t = content_data["topic"]
    uri = "/api/v1/topics/" + str(t.id) + "/reference-questions"
    assert (await client.get(uri)).status_code == 401
    await authenticate(client)
    response = await client.get(uri)
    assert response.status_code == 200, response.text
    assert response.json()["page"]["total"] == 2
    first = response.json()["data"][0]
    assert first["correct_option_ids"] == [str(content_data["options"][0][0].id)]
    assert "explanation" not in response.text and "DRAFT SECRET" not in response.text
    assert all("is_correct" not in option for option in first["options"])


@pytest.mark.parametrize("projection", ["exam", "learning"])
async def test_safe_projection_never_queries_or_serializes_answer_keys(
    content_client, content_data, projection
):
    client, app, _ = content_client
    await authenticate(client)
    from sqlalchemy import event

    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(app.state.database.engine.sync_engine, "before_cursor_execute", capture)
    try:
        r = await client.get(
            "/api/v1/test-definitions/" + str(content_data["definition"].id) + "/questions",
            params={"projection": projection, "mode": "exam"},
        )
    finally:
        event.remove(app.state.database.engine.sync_engine, "before_cursor_execute", capture)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 2
    for forbidden in (
        "is_correct",
        "correct_option_ids",
        "explanation",
        "fingerprint",
        "source_reference",
        "internal_difficulty",
    ):
        assert forbidden not in r.text
        assert all(forbidden not in statement for statement in statements)


async def test_search_normalization_literal_wildcards_and_original_number(
    content_client, content_data
):
    client, _, _ = content_client
    await authenticate(client)
    uri = "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions"
    assert len((await client.get(uri, params={"query": "ЕЖ ВРАЧ"})).json()["data"]) == 1
    assert len((await client.get(uri, params={"query": "%_"})).json()["data"]) == 1
    found = (await client.get(uri, params={"query": "длинный"})).json()["data"]
    assert len(found) == 1 and found[0]["number"] == 2
    assert (await client.get(uri, params={"query": "нет такого текста"})).json()["data"] == []
    topics = await client.get(
        "/api/v1/topics",
        params={
            "query": "СЛУЖЕБНАЯ " + content_data["suffix"],
            "discipline_id": str(content_data["d"].id),
        },
    )
    assert len(topics.json()["data"]) == 1


async def test_keyset_pagination_binding_and_version_invalidation(
    content_client, content_data, database
):
    client, _, _ = content_client
    await authenticate(client)
    uri = "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions"
    first = (await client.get(uri, params={"limit": 1})).json()
    assert first["page"]["has_more"]
    cursor = first["page"]["next_cursor"]
    second = (await client.get(uri, params={"limit": 1, "cursor": cursor})).json()
    assert (
        not second["page"]["has_more"]
        and first["data"][0]["question_id"] != second["data"][0]["question_id"]
    )
    assert (
        await client.get(uri, params={"cursor": cursor, "query": "different"})
    ).status_code == 400
    assert (await client.get(uri, params={"cursor": cursor[:-4] + "xxxx"})).status_code == 400
    safe = "/api/v1/test-definitions/" + str(content_data["definition"].id) + "/questions"
    assert (await client.get(safe, params={"cursor": cursor})).status_code == 400
    async with database.sessions.begin() as db:
        d = await db.get(Discipline, content_data["d"].id)
        d.title += " changed"
    assert (await client.get(uri, params={"cursor": cursor})).status_code == 409


async def test_draft_and_withdrawn_content_hidden_even_from_reviewer(
    content_client, content_data, database
):
    client, _, _ = content_client
    user = await authenticate(client)
    async with database.sessions.begin() as db:
        db.add(UserRole(user_id=UUID(user["user"]["id"]), role_code="content_reviewer"))
        revision = await db.get(QuestionRevision, content_data["revisions"][0].id)
        revision.status = "withdrawn"
    uri = "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions"
    result = await client.get(uri)
    assert result.status_code == 200 and result.json()["page"]["total"] == 1
    assert result.json()["data"][0]["question_id"] == str(content_data["questions"][1].id)
    async with database.sessions() as db:
        assert (await db.get(Question, content_data["questions"][0].id)).current_revision_id is None
    # Optional/withdrawn citation visibility is covered by rollback-isolated policy tests.
    assert (await client.get("/api/v1/disciplines/" + str(content_data["d"].id))).json()["data"][
        "question_count"
    ] == 1


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 31}, {"query": "x" * 201}, {"cursor": "x" * 2049}]
)
async def test_reference_limits(content_client, content_data, params):
    client, _, _ = content_client
    await authenticate(client)
    assert (
        await client.get(
            "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions",
            params=params,
        )
    ).status_code == 422


async def test_catalog_is_read_only_and_learning_requires_a_valid_command(
    content_client, content_data
):
    client, _, _ = content_client
    session = await authenticate(client)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}
    for path in (
        "/api/v1/disciplines",
        "/api/v1/topics",
        "/api/v1/test-definitions",
        "/api/v1/notes",
    ):
        assert (
            await client.post(path, json={"status": "published"}, headers=headers)
        ).status_code == 405
    assert (await client.post("/api/v1/attempts", json={}, headers=headers)).status_code == 422


async def test_plain_text_note_and_empty_unknown_material(content_client, content_data, database):
    client, _, _ = content_client
    await authenticate(client)
    data = content_data
    async with database.sessions.begin() as db:
        note = Note(
            id=uuid4(),
            discipline_id=data["d"].id,
            topic_id=data["topic"].id,
            slug=uuid4().hex,
            status="published",
        )
        db.add(note)
        await db.flush()
        rev = NoteRevision(
            id=uuid4(),
            note_id=note.id,
            revision_number=1,
            title="SYNTHETIC NOTE",
            sanitized_body="Plain text <literal>, not executable HTML",
            source_id=data["source"].id,
            created_by=data["author"],
            medical_review_by=data["reviewer"],
            reviewed_at=datetime.now(UTC),
            status="published",
        )
        db.add(rev)
        await db.flush()
        note.current_revision_id = rev.id
    response = await client.get("/api/v1/notes/" + str(note.id))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["body_format"] == "plain_text"
    assert response.json()["data"]["download_available"] is False
    listed = await client.get("/api/v1/notes", params={"discipline_id": str(data["d"].id)})
    assert listed.json()["page"]["total"] == 1
    assert "body" not in listed.json()["data"][0]
    assert (await client.get("/api/v1/assets/" + str(uuid4()) + "/download")).status_code == 404


@pytest.mark.parametrize("hidden", ["discipline", "category", "topic", "policy"])
async def test_unavailable_ancestors_and_policies_are_not_bypassed(
    content_client, content_data, database, hidden
):
    from app.content.models import AccessPolicy, Category, Topic

    client, _, _ = content_client
    await authenticate(client)
    async with database.sessions.begin() as db:
        if hidden == "policy":
            policy = AccessPolicy(
                id=uuid4(), code=uuid4().hex, requirement="unavailable", status="published"
            )
            db.add(policy)
            await db.flush()
            topic = await db.get(Topic, content_data["topic"].id)
            topic.access_policy_id = policy.id
        else:
            model = {"discipline": Discipline, "category": Category, "topic": Topic}[hidden]
            item = await db.get(model, content_data[{"discipline": "d"}.get(hidden, hidden)].id)
            item.status = "withdrawn"
    topic_id = str(content_data["topic"].id)
    assert (await client.get("/api/v1/topics/" + topic_id)).status_code == 404
    assert (
        await client.get("/api/v1/topics/" + topic_id + "/reference-questions")
    ).status_code == 404
    assert (
        await client.get(
            "/api/v1/test-definitions/" + str(content_data["definition"].id) + "/questions"
        )
    ).status_code == 404


async def test_private_cursor_is_bound_to_authenticated_owner(content_client, content_data):
    client, _, _ = content_client
    await authenticate(client)
    uri = "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions"
    first = await client.get(uri, params={"limit": 1})
    assert first.headers["Cache-Control"] == "no-store"
    cursor = first.json()["page"]["next_cursor"]
    client.cookies.clear()
    await authenticate(client)
    assert (await client.get(uri, params={"cursor": cursor})).status_code == 400


async def test_missing_read_role_is_denied(content_client, content_data, database):
    from sqlalchemy import delete

    from app.identity.models import User

    client, _, _ = content_client
    await authenticate(client)
    me = (await client.get("/api/v1/me")).json()["data"]
    async with database.sessions.begin() as db:
        user = await db.get(User, UUID(me["id"]))
        await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    uri = "/api/v1/topics/" + str(content_data["topic"].id) + "/reference-questions"
    assert (await client.get(uri)).status_code == 403
    assert (await client.get("/api/v1/notes")).status_code == 403


@pytest.mark.parametrize(
    "storage_key", ["valid", "../../private", "%2e%2e/secret", "bad\r\nheader"]
)
async def test_asset_download_requires_published_note_and_internal_delivery(
    content_client, content_data, database, storage_key
):
    from app.content.models import Asset

    client, app, settings = content_client
    key = "ab/" + "a" * 64 + ".pdf" if storage_key == "valid" else storage_key
    async with database.sessions.begin() as db:
        asset = Asset(
            id=uuid4(),
            storage_key=key,
            sha256="a" * 64,
            media_type="application/pdf",
            byte_size=100,
            status="published",
        )
        db.add(asset)
        await db.flush()
        note = Note(
            id=uuid4(), discipline_id=content_data["d"].id, slug=uuid4().hex, status="published"
        )
        db.add(note)
        await db.flush()
        revision = NoteRevision(
            id=uuid4(),
            note_id=note.id,
            revision_number=1,
            title="SYNTHETIC FILE NOTE",
            asset_id=asset.id,
            source_id=content_data["source"].id,
            created_by=content_data["author"],
            medical_review_by=content_data["reviewer"],
            reviewed_at=datetime.now(UTC),
            status="published",
        )
        db.add(revision)
        await db.flush()
        note.current_revision_id = revision.id
    uri = "/api/v1/assets/" + str(asset.id) + "/download"
    assert (await client.get(uri)).status_code == 401
    await authenticate(client)
    assert (await client.get(uri)).json()["error"]["code"] == "ASSET_DELIVERY_NOT_CONFIGURED"
    app.state.settings = settings.model_copy(update={"content_asset_delivery_enabled": True})
    response = await client.get(uri)
    if storage_key != "valid":
        assert response.status_code == 503 and "x-accel-redirect" not in response.headers
    else:
        assert response.status_code == 200
        assert response.headers["x-accel-redirect"] == "/internal/medexa-content/" + key
        assert (
            "storage_key" not in response.text and response.headers["cache-control"] == "no-store"
        )
        from sqlalchemy.exc import DBAPIError

        with pytest.raises(DBAPIError):
            async with database.sessions.begin() as db:
                stored = await db.get(Asset, asset.id)
                stored.storage_key = "cd/" + "b" * 64 + ".pdf"
        with pytest.raises(DBAPIError):
            async with database.sessions.begin() as db:
                stored_revision = await db.get(NoteRevision, revision.id)
                stored_revision.title = "CHANGED"
        detail = await client.get("/api/v1/notes/" + str(note.id))
        assert detail.json()["data"]["download_available"] is True
    async with database.sessions.begin() as db:
        n = await db.get(Note, note.id)
        n.status = "withdrawn"
    assert (await client.get(uri)).status_code == 404


async def test_definition_limit_counts_real_selected_questions(
    content_client, content_data, database
):
    from app.content.models import TestDefinition as Definition

    client, _, _ = content_client
    await authenticate(client)
    entity_id = str(content_data["definition"].id)
    async with database.sessions.begin() as db:
        definition = await db.get(Definition, content_data["definition"].id)
        definition.question_limit = 1
    result = await client.get("/api/v1/test-definitions/" + entity_id)
    assert result.json()["data"]["question_count"] == 1
    questions = await client.get("/api/v1/test-definitions/" + entity_id + "/questions")
    assert questions.json()["page"]["total"] == 1 and len(questions.json()["data"]) == 1


async def test_content_disabled_with_no_cursor_key(content_client, content_data):
    client, app, settings = content_client
    app.state.settings = settings.model_copy(update={"content_cursor_signing_key": None})
    response = await client.get("/api/v1/topics/" + str(content_data["topic"].id))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONTENT_NOT_CONFIGURED"
