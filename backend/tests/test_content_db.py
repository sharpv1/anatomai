import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.content.models import (
    ContentSource,
    Discipline,
    Note,
    Question,
    QuestionOption,
    QuestionRevision,
    Topic,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "target",
    [
        "text",
        "explanation",
        "option_update",
        "option_delete",
        "option_insert",
        "revision_delete",
        "question_delete",
        "source",
        "truncate",
    ],
)
async def test_published_history_is_immutable(database, content_data, target):
    d = content_data
    with pytest.raises(DBAPIError):
        async with database.sessions.begin() as db:
            if target in ("text", "explanation"):
                r = await db.get(QuestionRevision, d["revisions"][0].id)
                setattr(r, target, "CHANGED")
            elif target == "option_update":
                option = await db.get(QuestionOption, d["options"][0][0].id)
                option.is_correct = False
            elif target == "option_delete":
                await db.delete(await db.get(QuestionOption, d["options"][0][0].id))
            elif target == "option_insert":
                db.add(
                    QuestionOption(
                        id=uuid4(),
                        revision_id=d["revisions"][0].id,
                        position=9,
                        code="Z",
                        text="extra",
                        is_correct=False,
                    )
                )
            elif target == "revision_delete":
                await db.delete(await db.get(QuestionRevision, d["revisions"][0].id))
            elif target == "question_delete":
                await db.delete(await db.get(Question, d["questions"][0].id))
            elif target == "source":
                source = await db.get(ContentSource, d["source"].id)
                source.license_reference = "changed"
            else:
                await db.execute(text("TRUNCATE question_options"))


@pytest.mark.parametrize(
    "failure",
    ["no_reviewer", "same_author", "no_source", "no_correct", "two_correct", "multiple_choice"],
)
async def test_invalid_publication_is_rejected_at_commit(database, content_data, failure):
    d = content_data
    with pytest.raises(DBAPIError):
        async with database.sessions.begin() as db:
            revision = await db.get(QuestionRevision, d["revisions"][2].id)
            if failure == "no_reviewer":
                revision.medical_review_by = None
            if failure == "same_author":
                revision.medical_review_by = revision.created_by
            if failure == "no_source":
                revision.source_id = None
            if failure == "multiple_choice":
                revision.kind = "multiple_choice"
            if failure in ("no_correct", "two_correct"):
                for option in (
                    await db.scalars(
                        select(QuestionOption).where(QuestionOption.revision_id == revision.id)
                    )
                ).all():
                    option.is_correct = failure == "two_correct"
                await db.flush()
            revision.status = "published"


@pytest.mark.parametrize(
    "failure", ["draft_pointer", "foreign_pointer", "foreign_category", "foreign_note_topic"]
)
async def test_owner_and_published_pointer_constraints(database, content_data, failure):
    d = content_data
    with pytest.raises(DBAPIError):
        async with database.sessions.begin() as db:
            if failure in ("draft_pointer", "foreign_pointer"):
                q = await db.get(Question, d["questions"][0].id)
                q.current_revision_id = d["revisions"][2 if failure == "draft_pointer" else 1].id
            else:
                other = Discipline(
                    id=uuid4(),
                    slug=uuid4().hex,
                    title="OTHER TEST",
                    icon_key="test",
                    color_token="blue",
                )
                db.add(other)
                await db.flush()
                if failure == "foreign_category":
                    topic = await db.get(Topic, d["topic"].id)
                    topic.discipline_id = other.id
                else:
                    db.add(
                        Note(
                            id=uuid4(),
                            discipline_id=other.id,
                            topic_id=d["topic"].id,
                            slug=uuid4().hex,
                        )
                    )


async def test_new_revision_replaces_pointer_without_rewriting_old_history(database, content_data):
    d = content_data
    async with database.sessions.begin() as db:
        revision = QuestionRevision(
            id=uuid4(),
            question_id=d["questions"][0].id,
            revision_number=2,
            text="NEW SYNTHETIC VERSION",
            source_id=d["source"].id,
            created_by=d["author"],
            medical_review_by=d["reviewer"],
            reviewed_at=datetime.now(UTC),
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
                    code=str(i),
                    text="TEST",
                    is_correct=i == 0,
                )
                for i in range(2)
            ]
        )
        await db.flush()
        revision.status = "published"
        await db.flush()
        question = await db.get(Question, d["questions"][0].id)
        question.current_revision_id = revision.id
    async with database.sessions() as db:
        old = await db.get(QuestionRevision, d["revisions"][0].id)
        assert old.text == d["revisions"][0].text and old.status == "published"
        assert (await db.get(Question, question.id)).current_revision_id == revision.id


async def test_rights_cannot_be_marked_published_without_approval(database):
    with pytest.raises(DBAPIError):
        async with database.sessions.begin() as db:
            db.add(
                ContentSource(
                    id=uuid4(),
                    slug=uuid4().hex,
                    title="UNVERIFIED",
                    attribution="NO RIGHTS",
                    status="published",
                )
            )
