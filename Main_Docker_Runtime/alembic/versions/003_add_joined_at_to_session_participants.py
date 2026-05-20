"""add joined_at to session_participants

Revision ID: 003
Revises: 002
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'session_participants',
        sa.Column(
            'joined_at',
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
    )


def downgrade():
    op.drop_column('session_participants', 'joined_at')
