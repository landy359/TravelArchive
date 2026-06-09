"""add sdb columns to places + create alias table

Revision ID: 011
Revises: 010
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    # SDB 쿼리에서 사용하는 컬럼 추가 (기존 places 스키마 확장)
    op.add_column('places', sa.Column('main_category',   sa.String(50),  nullable=True))
    op.add_column('places', sa.Column('sub_category',    sa.String(255), nullable=True))
    op.add_column('places', sa.Column('address_road',    sa.String(255), nullable=True))
    op.add_column('places', sa.Column('region',          sa.String(100), nullable=True))
    op.add_column('places', sa.Column('region_depth_2',  sa.String(100), nullable=True))
    op.add_column('places', sa.Column('lat',             sa.Float(),     nullable=True))
    op.add_column('places', sa.Column('lon',             sa.Float(),     nullable=True))

    op.create_index('idx_places_main_category', 'places', ['main_category'])
    op.create_index('idx_places_region',        'places', ['region'])

    op.create_table(
        'alias',
        sa.Column('alias_id',  sa.String(50),  nullable=False),
        sa.Column('place_id',  sa.String(50),  sa.ForeignKey('places.place_id', ondelete='CASCADE'), nullable=False),
        sa.Column('alias',     sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('alias_id'),
    )
    op.create_index('idx_alias_place_id', 'alias', ['place_id'])


def downgrade():
    op.drop_table('alias')
    op.drop_index('idx_places_region',        table_name='places')
    op.drop_index('idx_places_main_category', table_name='places')
    op.drop_column('places', 'lon')
    op.drop_column('places', 'lat')
    op.drop_column('places', 'region_depth_2')
    op.drop_column('places', 'region')
    op.drop_column('places', 'address_road')
    op.drop_column('places', 'sub_category')
    op.drop_column('places', 'main_category')
