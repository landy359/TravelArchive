from typing import Any, Optional
from module.node.base.base import BaseProcessor
from backend.system.session_cache import SessionCache


class MemoNode(BaseProcessor):
    """
    메모 위젯 노드.

    버퍼: session_id → date_key → memo 문자열
    파사드 인터페이스: get(), set()
    NodeConnect 인터페이스: process(data) — LLM이 메모를 업데이트할 때 사용
    """

    def __init__(self):
        super().__init__()
        self._buffer: dict[str, dict[str, str]] = {}  # {session_id: {date_key: memo}}
        self._redis = None

    def bind_redis(self, redis):
        self._redis = redis

    # ── 파사드 인터페이스 ─────────────────────────────────────

    async def get(self, session_id: str, date_key: str) -> str:
        if session_id in self._buffer and date_key in self._buffer[session_id]:
            return self._buffer[session_id][date_key]
        memo = await SessionCache.get_memo(session_id, date_key, self._redis)
        self._buffer.setdefault(session_id, {})[date_key] = memo or ""
        return self._buffer[session_id][date_key]

    async def set(self, session_id: str, date_key: str, memo: str) -> None:
        self._buffer.setdefault(session_id, {})[date_key] = memo
        await SessionCache.save_memo(session_id, date_key, memo, self._redis)

    # ── NodeConnect 인터페이스 ────────────────────────────────

    async def process(self, data: Any) -> Optional[Any]:
        """
        LLM → 노드 방향 입력.
        data: {"session_id": str, "date_key": str, "memo": str}
        """
        if not isinstance(data, dict):
            self.signal("error", "expected dict")
            return None

        session_id = data.get("session_id")
        date_key = data.get("date_key")
        memo = data.get("memo")

        if not all([session_id, date_key, memo is not None]):
            self.signal("error", "missing fields")
            return None

        await self.set(session_id, date_key, memo)
        return {"widget": "memo", "session_id": session_id, "date_key": date_key, "memo": memo}
