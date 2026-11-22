import hashlib
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.models import Question, QuestionOption, QuestionRevision

pytestmark = pytest.mark.integration


async def test_downgrade_refuses_loss_of_immutable_license_metadata(database, actor):
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as db:
                async with db.begin():
                    q = Question(
                        id=uuid4(), external_source="synthetic-rollback", external_id=uuid4().hex
                    )
                    db.add(q)
                    await db.flush()
                    rev = QuestionRevision(
                        id=uuid4(),
                        question_id=q.id,
                        revision_number=1,
                        text="SYNTHETIC MIGRATION TEST",
                        license_reference="OPTIONAL METADATA",
                        created_by=actor,
                        fingerprint=hashlib.sha256(uuid4().bytes).hexdigest(),
                    )
                    db.add(rev)
                    await db.flush()
                    db.add_all(
                        [
                            QuestionOption(
                                id=uuid4(),
                                revision_id=rev.id,
                                position=i,
                                code=chr(65 + i),
                                text="TEST " + str(i),
                                is_correct=i == 0,
                            )
                            for i in range(2)
                        ]
                    )
                    await db.flush()
                    rev.status = "published"
                    await db.flush()
                    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            path = (
                Path(__file__).resolve().parents[1] / "migrations/versions/0006_import_staging.py"
            )
            spec = importlib.util.spec_from_file_location("import_revision", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def downgrade(conn):
                with Operations.context(MigrationContext.configure(conn)):
                    module.downgrade()

            with pytest.raises(RuntimeError, match="immutable history"):
                await connection.run_sync(downgrade)
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0010_progress_statistics"
            )
            assert await connection.scalar(text("SELECT to_regclass('import_jobs') IS NOT NULL"))
        finally:
            await transaction.rollback()
