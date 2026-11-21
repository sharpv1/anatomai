"""Verified identities, opaque sessions, roles and immutable security audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(256), nullable=False),
        sa.Column("last_name", sa.String(256)),
        sa.Column("username", sa.String(64)),
        sa.Column("photo_url", sa.String(2048)),
        sa.Column("language_code", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress_epoch", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        sa.CheckConstraint("telegram_user_id > 0", name=op.f("ck_users_telegram_id")),
        sa.CheckConstraint(
            "status IN ('active', 'blocked', 'anonymized')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint("version > 0 AND progress_epoch >= 0", name=op.f("ck_users_versions")),
    )
    roles = op.create_table(
        "roles",
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("description", sa.String(256), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_roles"),
    )
    op.bulk_insert(
        roles,
        [
            {"code": code, "description": description}
            for code, description in (
                ("student", "Own learning resources"),
                ("content_editor", "Content drafts"),
                ("content_reviewer", "Medical review"),
                ("support", "Limited support"),
                ("billing_admin", "Billing operations with MFA"),
                ("admin", "Administration with MFA"),
            )
        ],
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(32), nullable=False),
        sa.Column("granted_by", sa.Uuid()),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", "role_code", name="pk_user_roles"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_user_roles_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], ondelete="RESTRICT", name="fk_user_roles_granted_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["role_code"], ["roles.code"], ondelete="RESTRICT", name="fk_user_roles_role_code_roles"
        ),
    )
    op.create_index("ix_user_roles_role_code_user_id", "user_roles", ["role_code", "user_id"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_hash", sa.LargeBinary(), nullable=False),
        sa.Column("rotation_family_id", sa.Uuid(), nullable=False),
        *[
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("created_at", "last_seen_at", "expires_at", "idle_expires_at")
        ],
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        sa.UniqueConstraint("id", "user_id", name="uq_user_sessions_id_user_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_user_sessions_user_id_users"
        ),
        sa.CheckConstraint(
            "idle_expires_at <= expires_at AND expires_at > created_at "
            "AND idle_expires_at > created_at",
            name=op.f("ck_user_sessions_expiry"),
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32 AND octet_length(csrf_hash) = 32",
            name=op.f("ck_user_sessions_hashes"),
        ),
    )
    op.create_index(
        "ix_user_sessions_user_id_revoked_at", "user_sessions", ["user_id", "revoked_at"]
    )
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_table(
        "auth_replays",
        sa.Column("init_data_digest", sa.LargeBinary(), nullable=False),
        sa.Column("bot_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("init_data_digest", name="pk_auth_replays"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_auth_replays_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["user_sessions.id", "user_sessions.user_id"],
            ondelete="RESTRICT",
            name="fk_auth_replays_session_owner",
        ),
        sa.CheckConstraint(
            "octet_length(init_data_digest) = 32", name=op.f("ck_auth_replays_digest")
        ),
        sa.CheckConstraint("bot_id > 0", name=op.f("ck_auth_replays_bot_id")),
    )
    op.create_index("ix_auth_replays_session_id", "auth_replays", ["session_id"])
    op.create_index("ix_auth_replays_valid_until", "auth_replays", ["valid_until"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("safe_diff", postgresql.JSONB(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="RESTRICT", name="fk_audit_events_actor_id_users"
        ),
    )
    op.create_index(
        "ix_audit_events_actor_id_occurred_at", "audit_events", ["actor_id", "occurred_at"]
    )
    op.create_index(
        "ix_audit_events_entity_type_entity_id_occurred_at",
        "audit_events",
        ["entity_type", "entity_id", "occurred_at"],
    )
    op.execute("""CREATE FUNCTION medexa_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Audit events are immutable'; END; $$""")
    op.execute(
        "CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION medexa_audit_immutable()"
    )
    op.execute(
        "CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION medexa_audit_immutable()"
    )
    # Do not fabricate users or silently erase foundation cache rows to satisfy this FK.
    op.create_foreign_key(
        "fk_idempotency_requests_actor_id_users",
        "idempotency_requests",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_idempotency_requests_actor_id_users", "idempotency_requests", type_="foreignkey"
    )
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION medexa_audit_immutable()")
    op.drop_table("auth_replays")
    op.drop_table("user_sessions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
