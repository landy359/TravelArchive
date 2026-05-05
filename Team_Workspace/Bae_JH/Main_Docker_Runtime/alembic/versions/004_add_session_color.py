"""add color to sessions

Revision ID: 004
Revises: 003
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sessions',
        sa.Column('color', sa.String(20), nullable=True)
    )


def downgrade():
    op.drop_column('sessions', 'color')
