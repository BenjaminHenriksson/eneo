"""Persist latest-request context separately from cumulative token usage.

Revision ID: f73a2b180c41
Revises: 3eb6a34b6733
"""

import sqlalchemy as sa

from alembic import op

revision = "f73a2b180c41"
down_revision = "3eb6a34b6733"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "questions", sa.Column("context_tokens_question", sa.Integer(), nullable=True)
    )
    op.add_column(
        "questions", sa.Column("context_tokens_answer", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("questions", "context_tokens_answer")
    op.drop_column("questions", "context_tokens_question")
