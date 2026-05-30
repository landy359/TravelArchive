# [역할] 위젯 상태 조회·저장 실행 단위.
#        호출 방향: Facade → WidgetUnit → 각 위젯 매니저(정적) → Redis
from typing import Any

from .widget_trip_select import TripSelectWidget
from .widget_trip_clander import TripClanderWidget
from .widget_trip_map import TripMapWidget
from .widget_trip_marker import TripMarkerWidget
from .widget_trip_plan import TripPlanWidget
from .widget_trip_sel import TripSelWidget


class WidgetUnit:

    @staticmethod
    async def _scope(session_id: str, redis: Any) -> str:
        """trip 세션이면 trip:{trip_id}, 임시 세션이면 session:{session_id}."""
        trip_id = await redis.get_str(f"session:{session_id}:trip_id")
        return f"trip:{trip_id}" if trip_id else f"session:{session_id}"

    @staticmethod
    async def get_t_sl(session_id: str, redis: Any) -> str:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripSelectWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_t_sl(session_id: str, redis: Any, value: str) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripSelectWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_t_cd(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripClanderWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_t_cd(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripClanderWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_t_mp(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripMapWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_t_mp(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripMapWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_markers(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripMarkerWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_markers(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripMarkerWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_t_pn(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripPlanWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_t_pn(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripPlanWidget.save_to_redis(scope, redis, value)

    # ── 프론트 전용 (포맷 변환 포함) ─────────────────────────────

    @staticmethod
    async def get_t_sl_front(session_id: str, redis: Any) -> dict:
        from ...memory.cacher import Cacher
        scope = await WidgetUnit._scope(session_id, redis)
        raw = await TripSelectWidget.load_from_redis(scope, redis)
        if not raw:
            return {"visible": False, "options": []}

        sl_ctx = await Cacher.get_sl_ctx(session_id, redis)
        if sl_ctx and sl_ctx.get("A") and sl_ctx.get("B"):
            a_name = sl_ctx["A"].get("name", "A안")
            b_name = sl_ctx["B"].get("name", "B안")
            return {
                "visible": True,
                "options": [
                    {"key": "A", "label": "A안", "title": a_name, "value": f"A안: {a_name}"},
                    {"key": "B", "label": "B안", "title": b_name, "value": f"B안: {b_name}"},
                ],
            }

        widget = TripSelectWidget()
        widget.set_for_llm(raw)
        return widget.get_for_front()

    @staticmethod
    async def get_t_pn_front(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        raw = await TripPlanWidget.load_from_redis(scope, redis)
        widget = TripPlanWidget()
        widget.set_for_llm(raw)
        return widget.get_for_front()

    # ── 편집 선택 커서 (session-scoped) ─────────────────────────

    @staticmethod
    async def get_t_sel(session_id: str, redis: Any) -> dict:
        return await TripSelWidget.load_from_redis(f"session:{session_id}", redis)

    @staticmethod
    async def set_t_sel(session_id: str, redis: Any, value: dict) -> None:
        await TripSelWidget.save_to_redis(f"session:{session_id}", redis, value)

    # ── 지도/날짜 alias (facade API 호출명) ───────────────────────

    @staticmethod
    async def get_routes(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripMapWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_routes(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripMapWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_trip_range(session_id: str, redis: Any) -> list:
        scope = await WidgetUnit._scope(session_id, redis)
        return await TripClanderWidget.load_from_redis(scope, redis)

    @staticmethod
    async def set_trip_range(session_id: str, redis: Any, value: list) -> None:
        scope = await WidgetUnit._scope(session_id, redis)
        await TripClanderWidget.save_to_redis(scope, redis, value)

    @staticmethod
    async def get_trip_widgets_by_trip_id(trip_id: str, redis: Any, postgres: Any) -> dict:
        from ...memory.loader import Loader
        await Loader.hydrate_trip_plan_by_trip_id(trip_id, postgres, redis)
        scope = f"trip:{trip_id}"
        t_pn_raw = await TripPlanWidget.load_from_redis(scope, redis)
        t_cd = await TripClanderWidget.load_from_redis(scope, redis)
        t_mk = await TripMarkerWidget.load_from_redis(scope, redis)
        t_mp = await TripMapWidget.load_from_redis(scope, redis)
        pn_widget = TripPlanWidget()
        pn_widget.set_for_llm(t_pn_raw)
        return {
            "trip_id": trip_id,
            "t_cd": t_cd,
            "t_pn": pn_widget.get_for_front(),
            "t_mk": t_mk,
            "t_mp": t_mp,
        }
