"""
widget_trip_sel.py

T_SEL: 편집 대상 선택 커서.
  {"days": [0, 2]}  → 0-indexed 일차 선택 (day 1, day 3 수정)
  {}                → 선택 없음 (전체 수정 가능)

scope: 항상 session-scoped (session:{id}:widget:t_sel).
  trip 레벨 plan 데이터가 아닌 대화 세션의 편집 컨텍스트이므로
  세션마다 독립적인 커서를 가진다.
"""
from typing import Optional

from ...memory.constants import DATA_TTL

_REDIS_KEY = "widget:t_sel"


class TripSelWidget:

    @staticmethod
    async def save_to_redis(scope_key: str, redis, value: dict) -> None:
        await redis.set_json(f"{scope_key}:{_REDIS_KEY}", value or {}, DATA_TTL)

    @staticmethod
    async def load_from_redis(scope_key: str, redis) -> dict:
        data: Optional[dict] = await redis.get_json(f"{scope_key}:{_REDIS_KEY}")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def get_for_llm(value: dict) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def set_for_llm(value: dict) -> dict:
        return value if isinstance(value, dict) else {}
