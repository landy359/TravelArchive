# [역할] 지도 위젯(마커·경로)과 여행 기간 위젯을 처리하는 실행 단위.
#        MapNode, TripRangeNode는 Redis에 직접 붙어있는 인메모리 노드 객체이며,
#        이 실행 단위는 그 노드들을 첫 번째 인자로 받아 위임만 한다.
#        DB를 모른다. 위젯 데이터는 Redis 전용이며, 세션 blur/flush 시 MemoryManager가 처리한다.
#
#        호출 방향: facade → WidgetUnit → MapNode/TripRangeNode → Redis
from typing import Any


class WidgetUnit:

    @staticmethod
    async def add_marker(map_node: Any, session_id: str, marker_id: str, lat: float, lng: float, title: str) -> Any:
        return await map_node.add_marker(session_id, marker_id, lat, lng, title)

    @staticmethod
    async def delete_marker(map_node: Any, session_id: str, marker_id: str) -> Any:
        return await map_node.delete_marker(session_id, marker_id)

    @staticmethod
    async def set_markers(map_node: Any, session_id: str, markers: list) -> Any:
        return await map_node.set_markers(session_id, markers)

    @staticmethod
    async def get_markers(map_node: Any, session_id: str) -> Any:
        return await map_node.get_markers(session_id)

    @staticmethod
    async def set_routes(map_node: Any, session_id: str, marker_ids: list) -> Any:
        return await map_node.set_routes(session_id, marker_ids)

    @staticmethod
    async def get_routes(map_node: Any, session_id: str) -> Any:
        return await map_node.get_routes(session_id)

    @staticmethod
    async def set_trip_range(trip_range_node: Any, session_id: str, ranges: list) -> Any:
        return await trip_range_node.set(session_id, ranges)

    @staticmethod
    async def get_trip_range(trip_range_node: Any, session_id: str) -> Any:
        return await trip_range_node.get(session_id)

