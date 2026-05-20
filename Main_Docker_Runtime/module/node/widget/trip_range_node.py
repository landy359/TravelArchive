from typing import Any, Optional
from module.node.base.base import BaseProcessor
from backend.memory.cacher import Cacher as SessionCache


class TripRangeNode(BaseProcessor):
    """
    여행 날짜 범위 위젯 노드.

    버퍼: session_id → ranges (list of dict)
    파사드 인터페이스: get(), set()
    NodeConnect 인터페이스: process(data)
    """

    def __init__(self):
        super().__init__()
        self._buffer: dict[str, list] = {}
        self._redis = None

    def bind_redis(self, redis):
        self._redis = redis

    # ── 파사드 인터페이스 ─────────────────────────────────────

    async def get(self, session_id: str) -> list:
        if session_id not in self._buffer:
            self._buffer[session_id] = await SessionCache.get_ranges(session_id, self._redis) or []
        return self._buffer[session_id]

    async def set(self, session_id: str, ranges: list) -> None:
        self._buffer[session_id] = ranges
        await SessionCache.save_ranges(session_id, ranges, self._redis)

    # ── NodeConnect 인터페이스 ────────────────────────────────

    async def process(self, data: Any) -> Optional[Any]:
        """
        data: {"session_id": str, "ranges": list}
        """
        if not isinstance(data, dict):
            self.signal("error", "expected dict")
            return None

        session_id = data.get("session_id")
        ranges = data.get("ranges")

        if not all([session_id, ranges is not None]):
            self.signal("error", "missing fields")
            return None

        await self.set(session_id, ranges)
        return {"widget": "trip_range", "session_id": session_id, "ranges": ranges}
