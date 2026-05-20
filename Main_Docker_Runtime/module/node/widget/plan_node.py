from typing import Any, Optional
from module.node.base.base import BaseProcessor
from backend.system.session_cache import SessionCache


class PlanNode(BaseProcessor):
    """
    플래너 위젯 노드.

    버퍼: session_id → date_key → plan (list of dict)
    파사드 인터페이스: get(), set()
    NodeConnect 인터페이스: process(data)
    """

    def __init__(self):
        super().__init__()
        self._buffer: dict[str, dict[str, list]] = {}
        self._redis = None

    def bind_redis(self, redis):
        self._redis = redis

    # ── 파사드 인터페이스 ─────────────────────────────────────

    async def get(self, session_id: str, date_key: str) -> list:
        if session_id in self._buffer and date_key in self._buffer[session_id]:
            return self._buffer[session_id][date_key]
        plan = await SessionCache.get_plan(session_id, date_key, self._redis)
        self._buffer.setdefault(session_id, {})[date_key] = plan or []
        return self._buffer[session_id][date_key]

    async def set(self, session_id: str, date_key: str, plan: list) -> None:
        self._buffer.setdefault(session_id, {})[date_key] = plan
        await SessionCache.save_plan(session_id, date_key, plan, self._redis)

    # ── NodeConnect 인터페이스 ────────────────────────────────

    async def process(self, data: Any) -> Optional[Any]:
        """
        data: {"session_id": str, "date_key": str, "plan": list}
        """
        if not isinstance(data, dict):
            self.signal("error", "expected dict")
            return None

        session_id = data.get("session_id")
        date_key = data.get("date_key")
        plan = data.get("plan")

        if not all([session_id, date_key, plan is not None]):
            self.signal("error", "missing fields")
            return None

        await self.set(session_id, date_key, plan)
        return {"widget": "plan", "session_id": session_id, "date_key": date_key, "plan": plan}
