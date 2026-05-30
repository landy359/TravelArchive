from typing import List, Optional


class TripMapWidget:
    """T_MP: List[str] — 지도 폴리곤 노드 좌표 목록."""

    _REDIS_KEY = "widget:t_mp"

    def __init__(self) -> None:
        self._state: List[str] = []

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> List[str]:
        return self._state

    def set_for_llm(self, value: List[str]) -> None:
        self._state = list(value) if value else []

    # ── 프론트 경로 ────────────────────────────────────────────────
    # T_MP 는 LLM·프론트 형상이 동일(List[str])하므로 별도 변환 불필요.
    # 지도 렌더링 라이브러리가 요구하는 좌표 포맷(예: GeoJSON 등)이
    # 달라질 경우 아래 두 메서드에서 변환 구현.

    def get_for_front(self) -> List[str]:
        return self._state

    def set_for_front(self, value: List[str]) -> None:
        self._state = list(value) if value else []

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(scope_key: str, redis, value: List[str]) -> None:
        from ...memory.constants import DATA_TTL
        await redis.set_json(f"{scope_key}:{TripMapWidget._REDIS_KEY}", value or [], DATA_TTL)

    @staticmethod
    async def load_from_redis(scope_key: str, redis) -> List[str]:
        data: Optional[list] = await redis.get_json(f"{scope_key}:{TripMapWidget._REDIS_KEY}")
        return list(data) if data else []
