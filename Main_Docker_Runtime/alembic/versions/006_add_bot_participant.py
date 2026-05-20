"""006_add_bot_participant

봇은 인원수에서 체크 안 됨 — 오직 실제 유저만 개인/팀 구분에 사용.
- 시스템 봇 유저(user_id='bot') users 테이블에 추가
- 모든 기존 세션 session_participants에 bot(role='bot') 추가
- 이후 세션 생성 시 코드 레벨에서 bot을 자동 삽입
- participant_count = COUNT(*) - 1 (bot 슬롯 고정 차감 = 상수 -1)
"""

from alembic import op

revision  = '006'
down_revision = '005'
branch_labels = None
depends_on    = None


def upgrade():
    # 시스템 봇 유저 추가
    op.execute("""
        INSERT INTO users (user_id, user_type, status)
        VALUES ('bot', 'bot', 'active')
        ON CONFLICT (user_id) DO NOTHING
    """)

    # 모든 기존 세션에 bot 참여자 추가
    op.execute("""
        INSERT INTO session_participants (session_id, user_id, role, joined_at)
        SELECT session_id, 'bot', 'bot', created_at
        FROM sessions
        ON CONFLICT (session_id, user_id) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM session_participants WHERE user_id = 'bot'")
    op.execute("DELETE FROM users WHERE user_id = 'bot'")
