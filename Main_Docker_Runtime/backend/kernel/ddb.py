"""
[역할] dDB 조회 노드.
       QUST를 받아 dDB 필드를 채운 뒤 반환한다.

────────────────────────────────────────────────
입력 (QUST에서 읽는 필드)
────────────────────────────────────────────────
  qust.T_CD     : 날짜 범위 ["YYMMDD", ...]
                  → 여행 기간에 해당하는 날씨 레코드를 조회할 때 사용

  qust.SSN_TPC  : 세션 주제 ("제주도 3박4일" 등)
                  → location 추출 ("제주도" → "제주도" | "서귀포")

  qust.CC       : 현재 사용자 메시지
                  → T_CD·SSN_TPC가 없을 때 fallback

────────────────────────────────────────────────
출력 (QUST에 채우는 필드)
────────────────────────────────────────────────
  qust.dDB : List[dDB_Item]   (location × forecast_time 조합, 최대 80개)

  dDB_Item 필드:
    location        장소                      "제주도" | "서귀포"
    forecast_time   예보 시간대 (하루 4회)    "09" | "12" | "15" | "18"
    summary         날씨 개황                 ex) "맑음", "흐리고 비"
    rain_prob       강수 확률 (0~100)         ex) 30
    temperature     기온 (°C)                 ex) 22.5
    humidity        습도 (0~100)              ex) 65
    wind_speed      풍속 (m/s)                ex) 4.2
    etc............. (구현 생각해볼것, 위는 어디까지나 예시)
────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router.protocol import QUST
    from .db_connector import DBConnector

from .db_connector import DDB_TABLE


class DDB:

    def __init__(self, connector: "DBConnector") -> None:
        self._conn = connector

    async def run(self, qust: "QUST") -> "QUST":
        from ..router.protocol import dDB_Item

        # ── 구현 예시 ──────────────────────────────────
        # location = _extract_location(qust.SSN_TPC or qust.CC)
        # rows = await self._conn.select(
        #     DDB_TABLE,
        #     columns=["location", "forecast_time", "summary",
        #              "rain_prob", "temperature", "humidity", "wind_speed"],
        #     where={"location": location},
        #     limit=8,
        # )
        # qust.dDB = [dDB_Item.from_dict(r) for r in rows]
        # ───────────────────────────────────────────────

        return qust
