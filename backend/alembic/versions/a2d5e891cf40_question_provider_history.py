"""Retain provider reasoning and ordered tool rounds between chat turns."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a2d5e891cf40"
down_revision = "f73a2b180c41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "questions", sa.Column("provider_history", postgresql.JSONB(), nullable=True)
    )


def downgrade():
    op.drop_column("questions", "provider_history")
