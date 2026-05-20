from typing import Optional


class TripSelectWidget:
    """T_SL: str — 현재 선택된 여행지/옵션 (공백=없음)."""

    _REDIS_KEY = "widget:t_sl"

    def __init__(self) -> None:
        self._state: str = ""

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> str:
        return self._state

    def set_for_llm(self, value: str) -> None:
        self._state = value if isinstance(value, str) else ""

    # ── 프론트 경로 ────────────────────────────────────────────────
    # T_SL 은 LLM·프론트 형상이 동일(str)하므로 별도 변환 불필요.
    # 프론트 표출 형식이 달라질 경우 아래 두 메서드에서 변환 구현.

    def get_for_front(self) -> str:
        # TODO: 프론트 표출 형식으로 변환이 필요하면 여기서 구현
        return self._state

    def set_for_front(self, value: str) -> None:
        # TODO: 프론트 입력 형식 → _state 변환이 필요하면 여기서 구현
        self._state = value if isinstance(value, str) else ""

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: str) -> None:
        from ...memory.constants import DATA_TTL
        await redis.set_json(f"session:{session_id}:{TripSelectWidget._REDIS_KEY}", value or "", DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> str:
        data: Optional[str] = await redis.get_json(f"session:{session_id}:{TripSelectWidget._REDIS_KEY}")
        return data if isinstance(data, str) else ""
