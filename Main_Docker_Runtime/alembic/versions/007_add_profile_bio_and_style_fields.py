"""add bio to user_profile and profile_extra/style/travel to user_preferences

Revision ID: 007
Revises: 006
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user_profile: bio(자기소개), extra_contacts(추가 연락수단 JSONB 배열)
    op.add_column("user_profile",
        sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("user_profile",
        sa.Column("extra_contacts", postgresql.JSONB(), nullable=True))

    # user_preferences: style(AI 스타일), travel(여행 스타일) — ui_settings와 분리된 구조체
    # 기존 ui_settings는 UI 전용(투명도, 테마, 폰트, 알림) 유지
    # style, travel 은 계정 탭 개인화 전용
    op.add_column("user_preferences",
        sa.Column("style",  postgresql.JSONB(), nullable=True))
    op.add_column("user_preferences",
        sa.Column("travel", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "travel")
    op.drop_column("user_preferences", "style")
    op.drop_column("user_profile", "extra_contacts")
    op.drop_column("user_profile", "bio")
