"""Transaction-scoped idempotency foundation, no user/content/payment tables yet."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_projection", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_requests"),
        sa.UniqueConstraint("actor_id", "operation", "key", name="uq_idempotency_scope_key"),
        sa.CheckConstraint(
            "outcome IN ('processing', 'completed')", name=op.f("ck_idempotency_requests_outcome")
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_idempotency_requests_hash")
        ),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_idempotency_requests_expiry")),
        sa.CheckConstraint(
            "(outcome = 'processing' AND response_status IS NULL AND response_projection IS NULL) "
            "OR (outcome = 'completed' AND response_status IS NOT NULL "
            "AND response_status BETWEEN 200 AND 299 "
            "AND response_projection IS NOT NULL AND jsonb_typeof(response_projection) = 'object')",
            name=op.f("ck_idempotency_requests_response"),
        ),
    )
    op.create_index("ix_idempotency_requests_expires_at", "idempotency_requests", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_requests_expires_at", table_name="idempotency_requests")
    op.drop_table("idempotency_requests")
