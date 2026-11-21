"""Small immutable attribution dimension, history index and stable daily choice; no score copies."""

# ruff: noqa: E501 -- frozen DDL
import sqlalchemy as sa
from alembic import op

revision = "0010_progress_statistics"
down_revision = "0009_exam_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("attempt_items", sa.Column("topic_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_attempt_items_topic_id_topics"),
        "attempt_items",
        "topics",
        ["topic_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute("""CREATE FUNCTION medexa_attempt_topic_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.topic_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM attempts a JOIN topics t ON t.discipline_id=a.discipline_id
        JOIN topic_questions tq ON tq.topic_id=t.id
        WHERE a.id=NEW.attempt_id AND t.id=NEW.topic_id AND tq.question_id=NEW.question_id
        AND (a.topic_id IS NULL OR a.topic_id=NEW.topic_id)) THEN
        RAISE EXCEPTION 'Invalid snapshot topic attribution';
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute(
        "CREATE TRIGGER attempt_topic_guard BEFORE INSERT ON attempt_items FOR EACH ROW EXECUTE FUNCTION medexa_attempt_topic_guard()"
    )
    op.create_index(
        "ix_attempts_completed_history",
        "attempts",
        ["user_id", "progress_epoch", sa.text("finalized_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("status='completed'"),
    )
    op.create_table(
        "daily_recommendations",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column("local_date", sa.Date(), primary_key=True),
        sa.Column("topic_id", sa.Uuid(), sa.ForeignKey("topics.id", ondelete="RESTRICT")),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("selector_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("selector_version=1 AND catalog_version>=1", name="version"),
    )
    op.execute(
        "CREATE TRIGGER daily_recommendation_guard BEFORE UPDATE OR DELETE ON daily_recommendations FOR EACH ROW EXECUTE FUNCTION medexa_publication_command_guard()"
    )
    op.execute(
        "CREATE TRIGGER daily_recommendation_no_truncate BEFORE TRUNCATE ON daily_recommendations FOR EACH STATEMENT EXECUTE FUNCTION medexa_content_no_truncate()"
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM daily_recommendations) OR EXISTS(SELECT 1 FROM attempt_items WHERE topic_id IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "0010 downgrade blocked: progress attribution or daily history exists; use forward fix"
        )
    op.drop_table("daily_recommendations")
    op.drop_index("ix_attempts_completed_history", table_name="attempts")
    op.execute("DROP TRIGGER attempt_topic_guard ON attempt_items")
    op.execute("DROP FUNCTION medexa_attempt_topic_guard()")
    op.drop_constraint(
        op.f("fk_attempt_items_topic_id_topics"), "attempt_items", type_="foreignkey"
    )
    op.drop_column("attempt_items", "topic_id")
