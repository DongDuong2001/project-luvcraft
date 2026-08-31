"""separate Brand-IP collaboration from core research

Revision ID: 41b7c9d2e8f0
Revises: 8f3c1d7a2e90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "41b7c9d2e8f0"
down_revision: Union[str, Sequence[str], None] = "8f3c1d7a2e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("tenant_brand_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_research_runs_tenant_brand_id", "research_runs", "brand_profiles", ["tenant_brand_id"], ["brand_id"], ondelete="SET NULL")
    op.create_index("ix_research_runs_tenant_brand_id", "research_runs", ["tenant_brand_id"])
    op.execute("UPDATE research_runs SET tenant_brand_id = target_brand_id WHERE tenant_brand_id IS NULL")
    for column in (
        sa.Column("primary_offerings", sa.Text(), nullable=True),
        sa.Column("core_values", sa.Text(), nullable=True),
        sa.Column("mission", sa.Text(), nullable=True),
        sa.Column("primary_markets", sa.Text(), nullable=True),
        sa.Column("brand_tone", sa.Text(), nullable=True),
    ):
        op.add_column("brand_profiles", column)

    op.add_column("collaboration_candidates", sa.Column("normalized_name", sa.String(255), nullable=True))
    op.add_column("collaboration_candidates", sa.Column("brand_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_collaboration_candidates_brand_id", "collaboration_candidates", "brand_profiles", ["brand_id"], ["brand_id"], ondelete="CASCADE")
    op.create_index("ix_collaboration_candidates_normalized_name", "collaboration_candidates", ["normalized_name"])
    op.create_index("ix_collaboration_candidates_brand_id", "collaboration_candidates", ["brand_id"])
    op.create_unique_constraint("uq_collaboration_candidate_identity", "collaboration_candidates", ["brand_id", "normalized_name", "category"])
    op.execute("UPDATE collaboration_candidates SET category = 'IP' WHERE category IS NULL")
    op.alter_column("collaboration_candidates", "category", existing_type=sa.String(100), nullable=False, server_default="IP")

    op.add_column("run_candidate_selections", sa.Column("collaboration_goal", sa.String(50), nullable=True))
    for name, column_type in (
        ("candidate_metrics", postgresql.JSONB()),
        ("component_scores", postgresql.JSONB()),
        ("vibe_check", postgresql.JSONB()),
        ("evidence_references", postgresql.JSONB()),
        ("historical_performance", postgresql.JSONB()),
    ):
        op.add_column("candidate_evaluations", sa.Column(name, column_type, nullable=True))
    op.add_column("candidate_evaluations", sa.Column("provider_name", sa.String(100), nullable=True))
    op.add_column("candidate_evaluations", sa.Column("model_version", sa.String(100), nullable=True))
    op.add_column("candidate_evaluations", sa.Column("methodology_version", sa.String(100), nullable=True))
    op.add_column("candidate_evaluations", sa.Column("is_inferred", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade() -> None:
    for name in ("is_inferred", "methodology_version", "model_version", "provider_name", "historical_performance", "evidence_references", "vibe_check", "component_scores", "candidate_metrics"):
        op.drop_column("candidate_evaluations", name)
    op.drop_column("run_candidate_selections", "collaboration_goal")
    op.drop_constraint("uq_collaboration_candidate_identity", "collaboration_candidates", type_="unique")
    op.drop_index("ix_collaboration_candidates_brand_id", table_name="collaboration_candidates")
    op.drop_index("ix_collaboration_candidates_normalized_name", table_name="collaboration_candidates")
    op.drop_constraint("fk_collaboration_candidates_brand_id", "collaboration_candidates", type_="foreignkey")
    op.drop_column("collaboration_candidates", "brand_id")
    op.drop_column("collaboration_candidates", "normalized_name")
    for name in ("brand_tone", "primary_markets", "mission", "core_values", "primary_offerings"):
        op.drop_column("brand_profiles", name)
    op.drop_index("ix_research_runs_tenant_brand_id", table_name="research_runs")
    op.drop_constraint("fk_research_runs_tenant_brand_id", "research_runs", type_="foreignkey")
    op.drop_column("research_runs", "tenant_brand_id")
