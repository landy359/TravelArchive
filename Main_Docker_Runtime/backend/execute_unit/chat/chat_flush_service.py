"""
chat_flush_service.py  [domain / chat 카테고리]

역할:
  인터럽트 발생 시 Redis 세션 메타를 PostgreSQL로 내리는 플러시 전담 모듈.
  Execute Unit은 PG에 직접 접근하지 않고 Cacher → manager.emit 경로만 사용한다.
"""
from typing import Any


class FlushService:

    @staticmethod
    async def flush_single_session(session_id: str, redis: Any, manager: Any) -> None:
        """단일 세션의 Redis 메타를 Cacher를 통해 PG 반영 요청 후 Redis 정리."""
        from ...memory.cacher import Cacher

        meta = await Cacher.get_session_meta(session_id, redis)
        if not meta:
            return

        await Cacher.update_session_record(session_id, {
            "title": meta.get("name", "새 세션"),
            "topic": meta.get("topic", ""),
            "context_summary": meta.get("context", ""),
            "is_manual_title": meta.get("is_manual_title", "false") == "true",
        }, redis, manager)
        await Cacher.delete_session_cache(session_id, redis)

    @staticmethod
    async def flush_user_sessions(user_id: str, redis: Any, manager: Any) -> None:
        """사용자의 모든 활성 세션을 플러시하고 Redis 활성 목록을 정리."""
        from ...memory.cacher import Cacher

        session_ids = await Cacher.get_active_session_ids(user_id, redis)
        for session_id in session_ids:
            try:
                await FlushService.flush_single_session(session_id, redis, manager)
            except Exception as e:
                print(f"[FlushService] 세션 {session_id} 플러시 실패: {e}")
            await Cacher.unmark_active(user_id, session_id, redis)

        await Cacher.delete_current_session(user_id, redis)
        print(f"[FlushService] {user_id}: {len(session_ids)}개 세션 플러시 완료")
