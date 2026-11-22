"""Operator-provisioned MFA and draft-source ownership; no import/publication schema."""

import sqlalchemy as sa

# ruff: noqa: E501 -- frozen PostgreSQL DDL
from alembic import op

revision = "0004_admin"
down_revision = "0003_content"
branch_labels = None
depends_on = None

# Frozen PostgreSQL DDL. Never import mutable runtime models in migrations.
SCHEMA_SQL = (
    """CREATE TABLE admin_mfa_credentials (
	user_id UUID NOT NULL,
	encrypted_secret BYTEA NOT NULL,
	version BIGINT NOT NULL,
	last_counter BIGINT NOT NULL,
	failed_attempts INTEGER NOT NULL,
	locked_until TIMESTAMP WITH TIME ZONE,
	enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_admin_mfa_credentials PRIMARY KEY (user_id),
	CONSTRAINT ck_admin_mfa_credentials_versions CHECK (version > 0 AND last_counter >= -1),
	CONSTRAINT ck_admin_mfa_credentials_failures CHECK (failed_attempts BETWEEN 0 AND 5),
	CONSTRAINT ck_admin_mfa_credentials_ciphertext CHECK (octet_length(encrypted_secret) BETWEEN 100 AND 2048),
	CONSTRAINT fk_admin_mfa_credentials_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE admin_recovery_codes (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	code_hash BYTEA NOT NULL,
	credential_version BIGINT NOT NULL,
	used_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_admin_recovery_codes PRIMARY KEY (id),
	CONSTRAINT uq_admin_recovery_codes_owner_hash UNIQUE (user_id, code_hash),
	CONSTRAINT ck_admin_recovery_codes_hash_version CHECK (octet_length(code_hash) = 32 AND credential_version > 0),
	CONSTRAINT fk_admin_recovery_codes_user_id_admin_mfa_credentials FOREIGN KEY(user_id) REFERENCES admin_mfa_credentials (user_id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_admin_recovery_codes_user_id_used_at ON admin_recovery_codes (user_id, used_at)""",
    """CREATE TABLE admin_step_ups (
	session_id UUID NOT NULL,
	user_id UUID NOT NULL,
	credential_version BIGINT NOT NULL,
	roles_digest BYTEA NOT NULL,
	verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_admin_step_ups PRIMARY KEY (session_id),
	CONSTRAINT fk_admin_step_ups_session_owner FOREIGN KEY(session_id, user_id) REFERENCES user_sessions (id, user_id) ON DELETE CASCADE,
	CONSTRAINT ck_admin_step_ups_binding CHECK (credential_version > 0 AND octet_length(roles_digest) = 32),
	CONSTRAINT ck_admin_step_ups_freshness CHECK (expires_at > verified_at AND expires_at <= verified_at + interval '15 minutes'),
	CONSTRAINT fk_admin_step_ups_user_id_admin_mfa_credentials FOREIGN KEY(user_id) REFERENCES admin_mfa_credentials (user_id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_admin_step_ups_user_id_expires_at ON admin_step_ups (user_id, expires_at)""",
)


def upgrade():
    op.add_column("content_sources", sa.Column("created_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_content_sources_created_by_users",
        "content_sources",
        "users",
        ["created_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_content_sources_created_by", "content_sources", ["created_by"])
    op.create_check_constraint(
        op.f("ck_content_sources_independent_review"),
        "content_sources",
        "created_by IS NULL OR reviewed_by IS NULL OR created_by <> reviewed_by",
    )
    for statement in SCHEMA_SQL:
        op.execute(sa.text(statement))


def downgrade():
    op.drop_table("admin_step_ups")
    op.drop_table("admin_recovery_codes")
    op.drop_table("admin_mfa_credentials")
    op.drop_constraint(
        op.f("ck_content_sources_independent_review"), "content_sources", type_="check"
    )
    op.drop_index("ix_content_sources_created_by", table_name="content_sources")
    op.drop_constraint("fk_content_sources_created_by_users", "content_sources", type_="foreignkey")
    op.drop_column("content_sources", "created_by")
