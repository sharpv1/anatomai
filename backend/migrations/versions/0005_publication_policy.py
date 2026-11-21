"""Optional question provenance and structural-only publication gate.

No data is published, withdrawn, relabelled or medically approved by this migration.
"""
# ruff: noqa: E501 -- frozen SQL functions

import sqlalchemy as sa
from alembic import op

revision = "0005_publication_policy"
down_revision = "0004_admin"
branch_labels = None
depends_on = None

QUESTION_CHECK = """CREATE OR REPLACE FUNCTION medexa_content_question_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE q question_revisions%ROWTYPE; n int; c int;
BEGIN
IF TG_TABLE_NAME='question_options' THEN
 SELECT * INTO q FROM question_revisions WHERE id=COALESCE(NEW.revision_id,OLD.revision_id);
ELSE SELECT * INTO q FROM question_revisions WHERE id=NEW.id; END IF;
IF NOT FOUND OR q.status<>'published' THEN RETURN NULL; END IF;
SELECT count(*),count(*) FILTER(WHERE is_correct) INTO n,c FROM question_options WHERE revision_id=q.id;
IF n<2 OR n>8 OR q.kind<>'single_choice' OR c<>1 THEN
 RAISE EXCEPTION 'Unsupported published question or invalid answer key';
END IF;
IF q.text ~ '^[[:space:]]*$' OR EXISTS (
 SELECT 1 FROM question_options WHERE revision_id=q.id AND text ~ '^[[:space:]]*$'
) THEN RAISE EXCEPTION 'Published question and options must contain text'; END IF;
RETURN NULL; END; $$"""

RESTORE_QUESTION_CHECK = """CREATE OR REPLACE FUNCTION medexa_content_question_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE q question_revisions%ROWTYPE; n int; c int;
BEGIN
IF TG_TABLE_NAME='question_options' THEN
 SELECT * INTO q FROM question_revisions WHERE id=COALESCE(NEW.revision_id,OLD.revision_id);
ELSE SELECT * INTO q FROM question_revisions WHERE id=NEW.id; END IF;
IF NOT FOUND OR q.status<>'published' THEN RETURN NULL; END IF;
SELECT count(*),count(*) FILTER(WHERE is_correct) INTO n,c FROM question_options WHERE revision_id=q.id;
IF n<2 OR n>8 OR q.kind<>'single_choice' OR c<>1 THEN RAISE EXCEPTION 'Unsupported published question or invalid answer key'; END IF;
IF q.created_by IS NULL OR q.medical_review_by IS NULL OR q.created_by=q.medical_review_by OR q.reviewed_at IS NULL OR q.reviewed_at>clock_timestamp() OR NOT EXISTS (
 SELECT 1 FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE ur.user_id=q.medical_review_by AND ur.role_code='content_reviewer' AND u.status='active') OR NOT EXISTS (
 SELECT 1 FROM content_sources s WHERE s.id=q.source_id AND s.status='published')
THEN RAISE EXCEPTION 'Medical review and verified source are required'; END IF;
RETURN NULL; END; $$"""

RESTORE_SOURCE_CHECK = """CREATE FUNCTION medexa_content_source_check() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF NEW.status='published' AND (
 NEW.license_reference IS NULL OR length(trim(NEW.license_reference))=0 OR NEW.reviewed_at IS NULL OR NEW.reviewed_at>clock_timestamp() OR NOT EXISTS (
 SELECT 1 FROM user_roles ur JOIN users u ON u.id=ur.user_id WHERE ur.user_id=NEW.reviewed_by AND ur.role_code='content_reviewer' AND u.status='active'))
THEN RAISE EXCEPTION 'Verified content rights are required'; END IF;
RETURN NEW; END; $$"""


def upgrade():
    # A fresh upgrade includes 0003 seed DML in the same Alembic transaction.
    # Flush its deferred checks before altering their table.
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    op.alter_column(
        "question_revisions", "source_reference", existing_type=sa.Text(), nullable=True
    )
    op.drop_constraint(
        op.f("ck_content_sources_independent_review"), "content_sources", type_="check"
    )
    op.execute("DROP TRIGGER content_source_check ON content_sources")
    op.execute("DROP FUNCTION medexa_content_source_check()")
    op.execute(sa.text(QUESTION_CHECK))
    # Eligibility changed even without content DML: invalidate signed catalog cursors.
    op.execute("SET CONSTRAINTS ALL DEFERRED")
    op.execute(
        "UPDATE catalog_state SET version=version+1, changed_at=clock_timestamp() WHERE id=1"
    )


def downgrade():
    # Never invent citations/reviewers or mutate immutable published revisions for rollback.
    incompatible = op.get_bind().scalar(
        sa.text("""
SELECT EXISTS (SELECT 1 FROM question_revisions WHERE source_reference IS NULL
 OR (status='published' AND (created_by IS NULL OR medical_review_by IS NULL
 OR created_by=medical_review_by OR reviewed_at IS NULL OR source_id IS NULL
 OR NOT EXISTS (SELECT 1 FROM content_sources s WHERE s.id=question_revisions.source_id AND s.status='published'))))
 OR EXISTS (SELECT 1 FROM content_sources WHERE created_by=reviewed_by
 OR (status='published' AND (license_reference IS NULL OR length(trim(license_reference))=0
 OR reviewed_by IS NULL OR reviewed_at IS NULL)))
""")
    )
    if incompatible:
        raise RuntimeError(
            "0005 downgrade blocked: data uses the simplified policy; use a forward fix or a compatible backup"
        )
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    op.alter_column(
        "question_revisions", "source_reference", existing_type=sa.Text(), nullable=False
    )
    op.create_check_constraint(
        op.f("ck_content_sources_independent_review"),
        "content_sources",
        "created_by IS NULL OR reviewed_by IS NULL OR created_by <> reviewed_by",
    )
    op.execute(sa.text(RESTORE_SOURCE_CHECK))
    op.execute(
        "CREATE TRIGGER content_source_check BEFORE INSERT OR UPDATE ON content_sources FOR EACH ROW EXECUTE FUNCTION medexa_content_source_check()"
    )
    op.execute(sa.text(RESTORE_QUESTION_CHECK))
    op.execute("SET CONSTRAINTS ALL DEFERRED")
    op.execute(
        "UPDATE catalog_state SET version=version+1, changed_at=clock_timestamp() WHERE id=1"
    )
