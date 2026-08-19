"""add RBAC foundation

Revision ID: f7a8b9c0d1e2
Revises: 5f0b0560821e
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "5f0b0560821e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), server_default="viewer", nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('admin', 'analyst', 'client', 'viewer')",
            name=op.f("ck_user_profiles_user_profiles_role_check"),
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brand_profiles.brand_id"],
            name=op.f("fk_user_profiles_brand_id_brand_profiles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
        sa.UniqueConstraint("email", name=op.f("uq_user_profiles_email")),
    )
    op.create_index(op.f("ix_user_profiles_brand_id"), "user_profiles", ["brand_id"])
    op.create_index(op.f("ix_user_profiles_role"), "user_profiles", ["role"])

    op.create_table(
        "brand_domains",
        sa.Column(
            "domain_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("domain_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brand_profiles.brand_id"],
            name=op.f("fk_brand_domains_brand_id_brand_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("domain_id", name=op.f("pk_brand_domains")),
        sa.UniqueConstraint("domain_name", name=op.f("uq_brand_domains_domain_name")),
    )
    op.create_index(op.f("ix_brand_domains_brand_id"), "brand_domains", ["brand_id"])

    op.create_table(
        "api_keys",
        sa.Column(
            "key_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_profiles.user_id"],
            name=op.f("fk_api_keys_user_id_user_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key_id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column(
            "log_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("old_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["user_profiles.user_id"],
            name=op.f("fk_audit_logs_actor_id_user_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("log_id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"])
    op.create_index(op.f("ix_audit_logs_action_type"), "audit_logs", ["action_type"])
    op.create_index(
        "ix_audit_logs_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])

    op.add_column(
        "research_runs",
        sa.Column(
            "is_public_demo",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "is_public_demo")

    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_api_keys_user_id"), table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index(op.f("ix_brand_domains_brand_id"), table_name="brand_domains")
    op.drop_table("brand_domains")

    op.drop_index(op.f("ix_user_profiles_role"), table_name="user_profiles")
    op.drop_index(op.f("ix_user_profiles_brand_id"), table_name="user_profiles")
    op.drop_table("user_profiles")
