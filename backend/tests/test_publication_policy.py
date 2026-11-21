"""Policy changes use real PostgreSQL with rollback-only outer transactions.

HTTP commits release SAVEPOINTs; published test history is never deleted or bypassed.
"""

import hashlib
import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.content.api import disciplines_query
from app.content.models import (
    ContentSource,
    Discipline,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
    TopicQuestion,
)
from app.content.models import TestDefinition as Definition

pytestmark = pytest.mark.integration


@pytest.fixture
async def policy_context(admin_clients, database):
    async with admin_clients() as actor:
        async with database.engine.connect() as connection:
            outer = await connection.begin()
            sessions = async_sessionmaker(
                connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            previous = actor.app.state.database.sessions
            actor.app.state.database.sessions = sessions
            try:
                yield actor, sessions
            finally:
                await outer.rollback()
                actor.app.state.database.sessions = previous


async def publish_fixture(actor, sessions, source_status):
    async with sessions.begin() as db:
        discipline = Discipline(
            id=uuid4(),
            slug=uuid4().hex,
            title="SYNTHETIC POLICY",
            icon_key="test",
            color_token="blue",
            status="published",
        )
        db.add(discipline)
        await db.flush()
        topic = Topic(
            id=uuid4(),
            discipline_id=discipline.id,
            slug=uuid4().hex,
            title="SYNTHETIC POLICY TOPIC",
            status="published",
        )
        db.add(topic)
        await db.flush()
        definition = Definition(
            id=uuid4(),
            topic_id=topic.id,
            slug=uuid4().hex,
            title="SYNTHETIC POLICY TEST",
            exam_duration_seconds=60,
            status="published",
        )
        source = None
        if source_status is not None:
            source = ContentSource(
                id=uuid4(),
                slug=uuid4().hex,
                title="OPTIONAL METADATA",
                attribution="TEST ONLY",
                status=source_status,
                created_by=actor.user_id,
            )
            db.add(source)
        question = Question(id=uuid4(), external_source="synthetic-policy", external_id=uuid4().hex)
        db.add_all([question, definition])
        await db.flush()
        revision = QuestionRevision(
            id=uuid4(),
            question_id=question.id,
            revision_number=1,
            kind="single_choice",
            text="SYNTHETIC POLICY QUESTION",
            explanation="NOT FOR EXAM",
            source_id=source.id if source else None,
            source_reference=None,
            created_by=actor.user_id,
            fingerprint=hashlib.sha256(uuid4().bytes).hexdigest(),
        )
        db.add(revision)
        await db.flush()
        db.add_all(
            [
                QuestionOption(
                    id=uuid4(),
                    revision_id=revision.id,
                    position=i,
                    code=chr(65 + i),
                    text="SYNTHETIC OPTION " + str(i),
                    is_correct=i == 0,
                )
                for i in range(2)
            ]
        )
        db.add(TopicQuestion(topic_id=topic.id, question_id=question.id, position=0))
        await db.flush()
        revision.status = "published"
        await db.flush()
        question.current_revision_id = revision.id
        await db.flush()
        # Force deferred checks before rolling back the outer test transaction.
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert revision.medical_review_by is None and revision.reviewed_at is None
        return discipline, topic, definition, question, revision


@pytest.mark.parametrize("source_status", [None, "draft", "withdrawn"])
async def test_valid_publication_and_read_models_need_no_source_license_or_second_reviewer(
    policy_context, source_status
):
    actor, sessions = policy_context
    d, topic, definition, q, rev = await publish_fixture(actor, sessions, source_status)
    reference = await actor.client.get(f"/api/v1/topics/{topic.id}/reference-questions")
    assert reference.status_code == 200, reference.text
    assert reference.json()["page"]["total"] == 1
    assert reference.json()["data"][0]["question_id"] == str(q.id)
    assert len(reference.json()["data"][0]["correct_option_ids"]) == 1
    safe = await actor.client.get(f"/api/v1/test-definitions/{definition.id}/questions")
    assert safe.status_code == 200, safe.text
    assert len(safe.json()["data"]) == 1
    for key in (
        "is_correct",
        "explanation",
        "correct_option_ids",
        "medical_review_by",
        "source_reference",
    ):
        assert key not in safe.text
    async with sessions() as db:
        count = (
            (await db.execute(disciplines_query().where(Discipline.id == d.id))).mappings().one()
        )
        assert count["question_count"] == 1
    # Withdrawal still removes the question and clears its current pointer.
    async with sessions.begin() as db:
        stored = await db.get(QuestionRevision, rev.id)
        stored.status = "withdrawn"
    assert (await actor.client.get(f"/api/v1/topics/{topic.id}/reference-questions")).json()[
        "data"
    ] == []
    async with sessions() as db:
        assert (
            await db.scalar(select(Question.current_revision_id).where(Question.id == q.id)) is None
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"source_reference": None, "source_page": None},
        {"source_reference": "  ", "source_page": "\t"},
    ],
)
async def test_mfa_editor_can_create_own_draft_without_source_metadata(policy_context, metadata):
    actor, sessions = policy_context
    body = {
        "text": "SYNTHETIC OPTIONAL METADATA",
        "options": [
            {"code": "A", "text": "A", "is_correct": True},
            {"code": "B", "text": "B", "is_correct": False},
        ],
        **metadata,
    }
    result = await actor.client.post(
        "/api/v1/admin/questions", json=body, headers=await actor.write_headers()
    )
    assert result.status_code == 201, result.text
    revision = result.json()["data"]
    assert revision["created_by"] == str(actor.user_id) and revision["status"] == "draft"
    assert revision["source_id"] is None and revision["source_reference"] is None
    assert revision["medical_review_by"] is None
    async with sessions() as db:
        q = await db.get(Question, UUID(revision["question_id"]))
        assert q.current_revision_id is None  # Structural success is not automatic publication.


async def test_policy_rollback_refuses_new_data_instead_of_inventing_review(policy_context):
    actor, sessions = policy_context
    _, _, _, q, rev = await publish_fixture(actor, sessions, None)
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0005_publication_policy.py"
    spec = importlib.util.spec_from_file_location("policy_revision", path)
    revision_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision_module)

    def attempt(connection):
        with Operations.context(MigrationContext.configure(connection)):
            revision_module.downgrade()

    async with sessions.begin() as db:
        connection = await db.connection()
        with pytest.raises(RuntimeError, match="downgrade blocked"):
            await connection.run_sync(attempt)
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0007_publishing"
        stored = await db.get(QuestionRevision, rev.id)
        assert stored.status == "published" and stored.medical_review_by is None
        assert stored.source_reference is None and stored.source_id is None
        assert (
            await db.scalar(select(Question.current_revision_id).where(Question.id == q.id))
            == rev.id
        )
