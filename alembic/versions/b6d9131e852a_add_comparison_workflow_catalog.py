"""Add stable workflow names and persistent per-supplier-set numbering."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b6d9131e852a"
down_revision = "ceb9167fdd3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comparison_workflow_counters",
        sa.Column("procurement_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("procurement_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("supplier_key", sa.String(64), primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False),
    )
    op.create_table(
        "comparison_workflow_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("procurement_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("procurement_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_key", sa.String(64), nullable=False),
        sa.Column("supplier_ids", postgresql.JSONB(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("procurement_event_id", "supplier_key", "sequence_number", name="uq_workflow_group_number"),
    )
    op.create_index("ix_comparison_workflow_records_procurement_event_id", "comparison_workflow_records", ["procurement_event_id"])


def downgrade() -> None:
    op.drop_table("comparison_workflow_records")
    op.drop_table("comparison_workflow_counters")
