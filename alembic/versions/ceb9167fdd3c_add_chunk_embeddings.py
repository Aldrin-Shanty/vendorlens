"""add chunk embeddings

Revision ID: ceb9167fdd3c
Revises: 9204c5195b56
Create Date: 2026-10-06 20:57:26.697179
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ceb9167fdd3c"
down_revision: Union[str, Sequence[str], None] = "9204c5195b56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "chunks",
        sa.Column(
            "embedding",
            Vector(384),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "chunks",
        "embedding",
    )
