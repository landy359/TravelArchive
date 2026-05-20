"""add session created_by/mode, trip color/nullable fields

Revision ID: 002
Revises: 001
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # trips: color 컬럼 추가
    op.add_column("trips", sa.Column("color", sa.String(20), nullable=True))

    # trips: destination / start_date / end_date → nullable
    op.alter_column("trips", "destination", nullable=True)
    op.alter_column("trips", "start_date",  nullable=True)
    op.alter_column("trips", "end_date",    nullable=True)

    # sessions: created_by 컬럼 추가 (nullable FK)
    op.add_column("sessions",
        sa.Column("created_by", sa.String(40), nullable=True))
    op.create_foreign_key(
        "fk_sessions_created_by", "sessions", "users",
        ["created_by"], ["user_id"], ondelete="SET NULL")

    # sessions: mode 컬럼 추가
    op.add_column("sessions",
        sa.Column("mode", sa.String(20), nullable=False, server_default="personal"))


def downgrade() -> None:
    op.drop_column("sessions", "mode")
    op.drop_constraint("fk_sessions_created_by", "sessions", type_="foreignkey")
    op.drop_column("sessions", "created_by")
    op.alter_column("trips", "end_date",    nullable=False)
    op.alter_column("trips", "start_date",  nullable=False)
    op.alter_column("trips", "destination", nullable=False)
    op.drop_column("trips", "color")
