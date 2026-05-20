from typing import List, Optional


class TripClanderWidget:
    """T_CD: List[str] — 여행 날짜 범위 ["YYMMDD", ...]."""

    _REDIS_KEY = "widget:t_cd"

    def __init__(self) -> None:
        self._state: List[str] = []

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> List[str]:
        return self._state

    def set_for_llm(self, value: List[str]) -> None:
        self._state = list(value) if value else []

    # ── 프론트 경로 ────────────────────────────────────────────────
    # T_CD 는 LLM·프론트 형상이 동일(List[str])하므로 별도 변환 불필요.
    # 캘린더 위젯 표출 형식(예: "YYMMDD" → datetime 객체 등)이 달라질 경우
    # 아래 두 메서드에서 변환 구현.

    def get_for_front(self) -> List[str]:
        # TODO: 캘린더 위젯 표출 형식으로 변환이 필요하면 여기서 구현
        return self._state

    def set_for_front(self, value: List[str]) -> None:
        # TODO: 캘린더 위젯 입력 형식 → _state 변환이 필요하면 여기서 구현
        self._state = list(value) if value else []

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: List[str]) -> None:
        from ...memory.constants import DATA_TTL
        await redis.set_json(f"session:{session_id}:{TripClanderWidget._REDIS_KEY}", value or [], DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> List[str]:
        data: Optional[list] = await redis.get_json(f"session:{session_id}:{TripClanderWidget._REDIS_KEY}")
        return list(data) if data else []
