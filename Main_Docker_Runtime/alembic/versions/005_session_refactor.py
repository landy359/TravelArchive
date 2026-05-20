"""005_session_refactor

세션 로직 정비:
- sessions.mode 컬럼 제거 (팀/개인 구분은 participant_count > 1 런타임 판단)
- trips 테이블에 is_misc 플래그 추가 (is_misc=true 인 trip이 '기타')
- 사용자별 기타 trip은 애플리케이션 레이어에서 보장 (ensure_misc_trip)
"""

from alembic import op
import sqlalchemy as sa

revision  = '005'
down_revision = '004'
branch_labels = None
depends_on    = None


def upgrade():
    op.drop_column('sessions', 'mode')
    op.add_column('trips', sa.Column('is_misc', sa.Boolean(), nullable=False,
                                      server_default='false'))


def downgrade():
    op.add_column('sessions', sa.Column(
        'mode', sa.String(20), nullable=False, server_default='personal'))
    op.drop_column('trips', 'is_misc')
