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
        # TODO: 마커 위젯 표출 형식으로 변환 구현
        return self._state

    def set_for_front(self, value) -> None:
        # TODO: 마커 위젯 입력 형식 → T_MK_Item 변환 구현
        self.set_for_llm(value)

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: list) -> None:
        from ...memory.constants import DATA_TTL
        from ...router.protocol import T_MK_Item
        normalized = [
            item.to_dict() if isinstance(item, T_MK_Item) else item
            for item in (value or [])
        ]
        await redis.set_json(f"session:{session_id}:{TripMarkerWidget._REDIS_KEY}", normalized, DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> list:
        data: Optional[list] = await redis.get_json(f"session:{session_id}:{TripMarkerWidget._REDIS_KEY}")
        return data if data else []
