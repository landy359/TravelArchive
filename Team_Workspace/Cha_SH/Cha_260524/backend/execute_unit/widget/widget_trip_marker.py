from __future__ import annotations
from typing import List, Optional


class TripMarkerWidget:
    """
    T_MK: List[T_MK_Item]
    형상: { marker_id: str, place_info: PlaceInfo }

    인스턴스 메서드: Port2가 LLM 흐름 중 상태 보관용으로 사용.
    정적 메서드:     WidgetUnit이 Redis 직접 접근 시 사용.
    """

    _REDIS_KEY = "widget:t_mk"

    def __init__(self) -> None:
        self._state: list = []  # List[T_MK_Item]

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> list:
        return self._state

    def set_for_llm(self, value) -> None:
        from ...router.protocol import T_MK_Item
        if not value:
            self._state = []
            return
        self._state = [
            item if isinstance(item, T_MK_Item) else T_MK_Item.from_dict(item)
            for item in value
        ]

    # ── 프론트 경로 ────────────────────────────────────────────────
    # 마커 위젯 프론트 표출용. LLM 내부 형상(T_MK_Item)과
    # 프론트가 소비하는 형상이 다를 경우 아래 두 메서드에서 변환 구현.
    #
    # get_for_front 구현 가이드:
    #   - _state 는 List[T_MK_Item] (marker_id, place_info 포함 전체 정보)
    #   - 프론트 마커 카드/패널이 필요로 하는 필드만 추려서 반환
    #   - 예: [{"marker_id": .., "name": .., "lat": .., "lon": ..}, ...]
    #
    # set_for_front 구현 가이드:
    #   - 프론트(또는 Facade)에서 넘어온 마커 데이터를 T_MK_Item 으로 변환
    #   - set_for_llm() 재사용 가능

    def get_for_front(self) -> list:
        # 프론트엔드가 소비하는 평탄화된 형식으로 변환:
        # [{"marker_id": "...", "lat": 1.0, "lng": 2.0, "title": "...", ...}, ...]
        from ...router.protocol import T_MK_Item
        result = []
        for item in self._state:
            if isinstance(item, T_MK_Item):
                result.append({
                    "marker_id": item.marker_id,
                    "lat": item.place_info.lat,
                    "lng": item.place_info.lon,
                    "title": item.place_info.name,
                    "address_road": item.place_info.address_road,
                    "description": item.place_info.description,
                    "category": item.place_info.category
                })
            else:
                # 딕셔너리인 경우 (오류 방지)
                pi = item.get("place_info", {})
                result.append({
                    "marker_id": item.get("marker_id", ""),
                    "lat": pi.get("lat", 0.0) if pi else item.get("lat", 0.0),
                    "lng": pi.get("lon", 0.0) if pi else item.get("lng", 0.0),
                    "title": pi.get("name", "") if pi else item.get("title", ""),
                })
        return result

    def set_for_front(self, value) -> None:
        # 프론트엔드/API에서 넘어온 평탄화된 형식(lat/lng)을 T_MK_Item(place_info 중첩)으로 변환
        from ...router.protocol import T_MK_Item, PlaceInfo
        if not value:
            self._state = []
            return
        
        new_state = []
        for item in value:
            if isinstance(item, T_MK_Item):
                new_state.append(item)
            elif isinstance(item, dict):
                if "place_info" in item:
                    # 이미 중첩된 구조인 경우
                    new_state.append(T_MK_Item.from_dict(item))
                else:
                    # 프론트에서 온 평탄화된 구조인 경우
                    pi = PlaceInfo(
                        name=item.get("title", ""),
                        address_road=item.get("address_road", ""),
                        lat=float(item.get("lat", 0.0)),
                        lon=float(item.get("lng", 0.0)),
                        description=item.get("description", ""),
                        category=item.get("category", "")
                    )
                    new_state.append(T_MK_Item(marker_id=item.get("marker_id", ""), place_info=pi))
        self._state = new_state

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: list) -> None:
        from ...memory.constants import DATA_TTL
        from ...router.protocol import T_MK_Item, PlaceInfo
        normalized = []
        for item in (value or []):
            if isinstance(item, T_MK_Item):
                normalized.append(item.to_dict())
            elif isinstance(item, dict):
                if "place_info" in item:
                    normalized.append(item)
                else:
                    pi = PlaceInfo(
                        name=item.get("title", ""),
                        address_road=item.get("address_road", ""),
                        lat=float(item.get("lat", 0.0)),
                        lon=float(item.get("lng", 0.0)),
                        description=item.get("description", ""),
                        category=item.get("category", "")
                    )
                    normalized.append(T_MK_Item(marker_id=item.get("marker_id", ""), place_info=pi).to_dict())
            else:
                normalized.append(item)
        await redis.set_json(f"session:{session_id}:{TripMarkerWidget._REDIS_KEY}", normalized, DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> list:
        data: Optional[list] = await redis.get_json(f"session:{session_id}:{TripMarkerWidget._REDIS_KEY}")
        return data if data else []
