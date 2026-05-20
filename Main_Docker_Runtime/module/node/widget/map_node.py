from typing import Any, Optional
from module.node.base.base import BaseProcessor
from backend.memory.cacher import Cacher as SessionCache


class MapNode(BaseProcessor):
    """
    지도 위젯 노드 (markers + routes).

    버퍼: session_id → {markers: list, routes: list}
    파사드 인터페이스: get_markers(), set_markers(), get_routes(), set_routes()
    NodeConnect 인터페이스: process(data)
    """

    def __init__(self):
        super().__init__()
        self._buffer: dict[str, dict] = {}  # {session_id: {"markers": [], "routes": []}}
        self._redis = None

    def bind_redis(self, redis):
        self._redis = redis

    def _buf(self, session_id: str) -> dict:
        if session_id not in self._buffer:
            self._buffer[session_id] = {"markers": None, "routes": None}
        return self._buffer[session_id]

    # ── 파사드 인터페이스 ─────────────────────────────────────

    async def get_markers(self, session_id: str) -> list:
        buf = self._buf(session_id)
        if buf["markers"] is None:
            buf["markers"] = await SessionCache.get_markers(session_id, self._redis) or []
        return buf["markers"]

    async def set_markers(self, session_id: str, markers: list) -> None:
        normalized = []
        for m in markers:
            mid = m.get("marker_id") or m.get("id")
            if mid:
                normalized.append({
                    "marker_id": mid,
                    "lat":   m.get("lat", 0),
                    "lng":   m.get("lng", 0),
                    "title": m.get("title", ""),
                })
        self._buf(session_id)["markers"] = normalized
        await SessionCache.save_markers(session_id, normalized, self._redis)

    async def add_marker(self, session_id: str, marker_id: str,
                         lat: float, lng: float, title: str) -> None:
        markers = await self.get_markers(session_id)
        markers = [m for m in markers if m.get("marker_id") != marker_id]
        markers.append({"marker_id": marker_id, "lat": lat, "lng": lng, "title": title})
        self._buf(session_id)["markers"] = markers
        await SessionCache.save_markers(session_id, markers, self._redis)

    async def delete_marker(self, session_id: str, marker_id: str) -> None:
        markers = await self.get_markers(session_id)
        markers = [m for m in markers if m.get("marker_id") != marker_id]
        self._buf(session_id)["markers"] = markers
        await SessionCache.save_markers(session_id, markers, self._redis)

    async def get_routes(self, session_id: str) -> list:
        buf = self._buf(session_id)
        if buf["routes"] is None:
            buf["routes"] = await SessionCache.get_routes(session_id, self._redis) or []
        return buf["routes"]

    async def set_routes(self, session_id: str, marker_ids: list) -> None:
        self._buf(session_id)["routes"] = marker_ids
        await SessionCache.save_routes(session_id, marker_ids, self._redis)

    # ── NodeConnect 인터페이스 ────────────────────────────────

    async def process(self, data: Any) -> Optional[Any]:
        """
        data: {"session_id": str, "action": "markers"|"routes", "data": list}
        """
        if not isinstance(data, dict):
            self.signal("error", "expected dict")
            return None

        session_id = data.get("session_id")
        action = data.get("action")
        payload = data.get("data")

        if not all([session_id, action, payload is not None]):
            self.signal("error", "missing fields")
            return None

        if action == "markers":
            await self.set_markers(session_id, payload)
            return {"widget": "map", "action": "markers", "session_id": session_id, "data": payload}

        if action == "routes":
            await self.set_routes(session_id, payload)
            return {"widget": "map", "action": "routes", "session_id": session_id, "data": payload}

        self.signal("error", f"unknown action: {action}")
        return None
