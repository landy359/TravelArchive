"""add analysis column to user_preferences

Revision ID: 008
Revises: 007
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences",
        sa.Column("analysis", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "analysis")
