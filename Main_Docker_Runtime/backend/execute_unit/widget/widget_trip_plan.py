from __future__ import annotations
from typing import List, Optional


class TripPlanWidget:
    """
    T_PN: List[List[T_PN_Item]]  (최대 7일 × 10개 행렬)
    형상: { date: str(YYMMDD), order: int, place: str, place_info: PlaceInfo }

    인스턴스 메서드: Port2가 LLM 흐름 중 상태 보관용으로 사용.
    정적 메서드:     WidgetUnit이 Redis 직접 접근 시 사용.
    """

    _REDIS_KEY = "widget:t_pn"

    def __init__(self) -> None:
        self._state: list = []  # List[List[T_PN_Item]]

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> list:
        return self._state

    def set_for_llm(self, value) -> None:
        from ...router.protocol import T_PN_Item
        if not value:
            self._state = []
            return
        self._state = [
            [
                item if isinstance(item, T_PN_Item) else T_PN_Item.from_dict(item)
                for item in row
            ]
            for row in value
        ]

    # ── 프론트 경로 ────────────────────────────────────────────────
    # 일정표 위젯 프론트 표출용. LLM 내부 형상(T_PN_Item 2D 행렬)과
    # 프론트가 소비하는 형상이 다를 경우 아래 두 메서드에서 변환 구현.
    #
    # get_for_front 구현 가이드:
    #   - _state 는 List[List[T_PN_Item]] (7일 × 최대 10개)
    #   - 일정표 UI가 필요로 하는 형식으로 재구성
    #   - 예: 날짜별 그룹핑, 빈 슬롯 채우기, 표시용 필드만 추출 등
    #
    # set_for_front 구현 가이드:
    #   - 프론트(또는 Facade)에서 넘어온 일정 데이터를 T_PN_Item 행렬로 변환
    #   - set_for_llm() 재사용 가능

    def get_for_front(self) -> list:
        from ...router.protocol import T_PN_Item

        result = []
        for day_idx, row in enumerate(self._state):
            if not isinstance(row, list):
                continue

            items = []
            day_date = ""
            for item in row:
                if isinstance(item, T_PN_Item):
                    day_date = item.date or day_date
                    items.append({
                        "order":      item.order,
                        "place":      item.place,
                        "place_info": item.place_info.to_dict()
                                      if hasattr(item.place_info, "to_dict")
                                      else (item.place_info or {}),
                    })
                elif isinstance(item, dict):
                    day_date = item.get("date", "") or day_date
                    items.append({
                        "order":      item.get("order", 0),
                        "place":      item.get("place", ""),
                        "place_info": item.get("place_info", {}),
                    })

            result.append({
                "day":   day_idx + 1,
                "date":  day_date,
                "items": items,
            })

        return result

    def set_for_front(self, value) -> None:
        if not value:
            self._state = []
            return

        converted = []
        for day_obj in value:
            if not isinstance(day_obj, dict):
                continue

            day_date = day_obj.get("date", "")
            row = []
            for item in day_obj.get("items", []):
                if not isinstance(item, dict):
                    continue
                row.append({
                    "date":       item.get("date", day_date),
                    "order":      item.get("order", 0),
                    "place":      item.get("place", ""),
                    "place_info": item.get("place_info", {}),
                })
            converted.append(row)

        self.set_for_llm(converted)

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: list) -> None:
        from ...memory.constants import DATA_TTL
        from ...router.protocol import T_PN_Item
        normalized = [
            [item.to_dict() if isinstance(item, T_PN_Item) else item for item in row]
            for row in (value or [])
        ]
        await redis.set_json(f"session:{session_id}:{TripPlanWidget._REDIS_KEY}", normalized, DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> list:
        data: Optional[list] = await redis.get_json(f"session:{session_id}:{TripPlanWidget._REDIS_KEY}")
        return data if data else []
