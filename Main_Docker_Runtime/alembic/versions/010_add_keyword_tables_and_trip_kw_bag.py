"""add keyword_encyclopedia, trip_keyword_scores

Revision ID: 010
Revises: 009
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'keyword_encyclopedia',
        sa.Column('keyword',    sa.String(100), primary_key=True),
        sa.Column('category',   sa.String(50),  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    op.create_table(
        'trip_keyword_scores',
        sa.Column('trip_id',    sa.String(50),  sa.ForeignKey('trips.trip_id', ondelete='CASCADE'), nullable=False),
        sa.Column('keyword',    sa.String(100), sa.ForeignKey('keyword_encyclopedia.keyword', ondelete='CASCADE'), nullable=False),
        sa.Column('score',      sa.Float(),     nullable=False, server_default='0.0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('trip_id', 'keyword'),
    )


def downgrade():
    op.drop_table('trip_keyword_scores')
    op.drop_table('keyword_encyclopedia')
