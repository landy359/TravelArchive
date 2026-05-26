# [역할] 위젯 상태 조회·저장 실행 단위.
#        호출 방향: Facade → WidgetUnit → 각 위젯 매니저(정적) → Redis
from typing import Any

from .widget_trip_select import TripSelectWidget
from .widget_trip_clander import TripClanderWidget
from .widget_trip_map import TripMapWidget
from .widget_trip_marker import TripMarkerWidget
from .widget_trip_plan import TripPlanWidget


class WidgetUnit:

    @staticmethod
    async def get_t_sl(session_id: str, redis: Any) -> str:
        return await TripSelectWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_t_sl(session_id: str, redis: Any, value: str) -> None:
        await TripSelectWidget.save_to_redis(session_id, redis, value)

    @staticmethod
    async def get_t_cd(session_id: str, redis: Any) -> list:
        return await TripClanderWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_t_cd(session_id: str, redis: Any, value: list) -> None:
        await TripClanderWidget.save_to_redis(session_id, redis, value)

    @staticmethod
    async def get_t_mp(session_id: str, redis: Any) -> list:
        return await TripMapWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_t_mp(session_id: str, redis: Any, value: list) -> None:
        await TripMapWidget.save_to_redis(session_id, redis, value)

    @staticmethod
    async def get_markers(session_id: str, redis: Any) -> list:
        return await TripMarkerWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_markers(session_id: str, redis: Any, value: list) -> None:
        await TripMarkerWidget.save_to_redis(session_id, redis, value)

    @staticmethod
    async def get_t_pn(session_id: str, redis: Any) -> list:
        return await TripPlanWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_t_pn(session_id: str, redis: Any, value: list) -> None:
        await TripPlanWidget.save_to_redis(session_id, redis, value)

    # ── 프론트 전용 (포맷 변환 포함) ─────────────────────────────

    @staticmethod
    async def get_t_sl_front(session_id: str, redis: Any) -> dict:
        raw = await TripSelectWidget.load_from_redis(session_id, redis)
        widget = TripSelectWidget()
        widget.set_for_llm(raw)
        return widget.get_for_front()

    @staticmethod
    async def get_t_pn_front(session_id: str, redis: Any) -> list:
        raw = await TripPlanWidget.load_from_redis(session_id, redis)
        widget = TripPlanWidget()
        widget.set_for_llm(raw)
        return widget.get_for_front()

    # ── 구버전 호환 (facade 기존 호출명) ──────────────────────────

    @staticmethod
    async def get_routes(session_id: str, redis: Any) -> list:
        return await TripMapWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_routes(session_id: str, redis: Any, value: list) -> None:
        await TripMapWidget.save_to_redis(session_id, redis, value)

    @staticmethod
    async def get_trip_range(session_id: str, redis: Any) -> list:
        return await TripClanderWidget.load_from_redis(session_id, redis)

    @staticmethod
    async def set_trip_range(session_id: str, redis: Any, value: list) -> None:
        await TripClanderWidget.save_to_redis(session_id, redis, value)
