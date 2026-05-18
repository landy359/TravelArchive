"""
chat_session_cache.py  [domain / chat 카테고리]

역할:
  Cacher에 대한 얇은 위임 레이어. 직접 Redis 접근 없음.
  SessionContainer·ChatService가 이 클래스를 통해 Cacher에 접근.
"""
from ...memory.cacher import Cacher

SESSION_TTL          = 3600 * 8
USER_SESSION_SET_TTL = 3600 * 24
DATA_TTL             = 3600 * 24


class SessionCache:

    # ── 활성 세션 Set 관리 ────────────────────────────────────

    @staticmethod
    async def mark_active(user_id: str, session_id: str, redis):
        await Cacher.mark_active(user_id, session_id, redis)

    @staticmethod
    async def unmark_active(user_id: str, session_id: str, redis):
        await Cacher.unmark_active(user_id, session_id, redis)

    @staticmethod
    async def get_active_session_ids(user_id: str, redis) -> set:
        return await Cacher.get_active_session_ids(user_id, redis)

    # ── 현재 세션 추적 ────────────────────────────────────────

    @staticmethod
    async def set_current_session(user_id: str, session_id: str, redis):
        await Cacher.set_current_session(user_id, session_id, redis)

    @staticmethod
    async def get_current_session(user_id: str, redis):
        return await Cacher.get_current_session(user_id, redis)

    # ── 세션 메타 캐시 ───────────────────────────────────────

    @staticmethod
    async def cache_session_meta(session_id: str, meta: dict, redis):
        await Cacher.cache_session_meta(session_id, meta, redis)

    @staticmethod
    async def get_session_meta(session_id: str, redis):
        return await Cacher.get_session_meta(session_id, redis)

    @staticmethod
    async def delete_session_cache(session_id: str, redis):
        await Cacher.delete_session_cache(session_id, redis)

    # ── 마커 ────────────────────────────────────────────────

    @staticmethod
    async def save_markers(session_id: str, markers: list, redis):
        await Cacher.save_markers(session_id, markers, redis)

    @staticmethod
    async def get_markers(session_id: str, redis) -> list:
        return await Cacher.get_markers(session_id, redis)

    # ── 폴리라인 경로 ────────────────────────────────────────

    @staticmethod
    async def save_routes(session_id: str, marker_ids: list, redis):
        await Cacher.save_routes(session_id, marker_ids, redis)

    @staticmethod
    async def get_routes(session_id: str, redis) -> list:
        return await Cacher.get_routes(session_id, redis)

    # ── 여행 기간 ─────────────────────────────────────────────

    @staticmethod
    async def save_ranges(session_id: str, ranges: list, redis):
        await Cacher.save_ranges(session_id, ranges, redis)

    @staticmethod
    async def get_ranges(session_id: str, redis) -> list:
        return await Cacher.get_ranges(session_id, redis)

    # ── 메모 ──────────────────────────────────────────────────

    @staticmethod
    async def save_memo(session_id: str, date_key: str, memo: str, redis):
        await Cacher.save_memo(session_id, date_key, memo, redis)

    @staticmethod
    async def get_memo(session_id: str, date_key: str, redis) -> str:
        return await Cacher.get_memo(session_id, date_key, redis)

    # ── 플래너 ────────────────────────────────────────────────

    @staticmethod
    async def save_plan(session_id: str, date_key: str, plan: list, redis):
        await Cacher.save_plan(session_id, date_key, plan, redis)

    @staticmethod
    async def get_plan(session_id: str, date_key: str, redis) -> list:
        return await Cacher.get_plan(session_id, date_key, redis)

    # ── 캘린더 인디케이터 ────────────────────────────────────

    @staticmethod
    async def get_indicators(session_id: str, year: int, month: int, redis) -> list:
        return await Cacher.get_indicators(session_id, year, month, redis)
