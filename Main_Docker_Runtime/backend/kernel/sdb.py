"""
[역할] sDB 조회 노드.
       QUST를 받아 sDB 필드를 채운 뒤 반환한다.

────────────────────────────────────────────────
입력 (QUST에서 읽는 필드)
────────────────────────────────────────────────
  qust.SSN_TPC  : 세션 주제 ("제주도 3박4일 여행" 등)
                  → 여기서 지역(region) 키워드를 추출해 WHERE 조건으로 사용

  qust.CC       : 현재 사용자 메시지 ("맛집 추천해줘", "카페 알려줘" 등)
                  → SSN_TPC가 없을 때 fallback, 카테고리 힌트 추출에도 활용

────────────────────────────────────────────────
출력 (QUST에 채우는 필드)
────────────────────────────────────────────────
  qust.sDB : List[sDB_Item]   (최대 k개, 현재 limit=20 예시)

  sDB_Item 필드:
    place_id        장소 고유 식별자          ex) "jeju_0042"
    name            상호명                    ex) "흑돼지식당"
    main_category   메인 카테고리             "식당" | "카페" | "관광지" | "포토스팟"
    sub_category    서브 카테고리 (카카오 분류) ex) "음식점>돼지고기구이"
    address_road    도로명주소                ex) "제주특별자치도 제주시 ..."
    lat             위도                      ex) 33.4996
    lon             경도                      ex) 126.5312
    region          권역                      "북부" | "동부" | "서부" | "남부"
    region_depth_2  시 단위 구분              "제주시" | "서귀포시"
    alias           별칭                      ex) "흑돼지 거리"
    etc............. (구현 생각해볼것, 위는 어디까지나 예시)
────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router.protocol import QUST
    from .db_connector import DBConnector

from .db_connector import SDB_TABLE


class SDB:

    def __init__(self, connector: "DBConnector") -> None:
        self._conn = connector

    async def run(self, qust: "QUST") -> "QUST":
        from ..router.protocol import sDB_Item

        # ── 구현 예시 ──────────────────────────────────
        # keyword = _extract_region(qust.SSN_TPC or qust.CC)
        # rows = await self._conn.select(
        #     SDB_TABLE,
        #     columns=["place_id", "name", "main_category", "sub_category",
        #              "address_road", "lat", "lon", "region", "region_depth_2", "alias"],
        #     where={"region": keyword},
        #     limit=20,
        # )
        # qust.sDB = [sDB_Item.from_dict(r) for r in rows]
        # ───────────────────────────────────────────────

        return qust
