"""
[역할] sDB 조회 노드. 제주도 전용.

────────────────────────────────────────────────
흐름
────────────────────────────────────────────────
  1. 의도 추출: LLM 1회 호출 (days, keywords JSON 파싱)
  2. 앵커 설정: 
     - day가 없다면 '제주시' 고정
     - 일수가 있다면 '제주시 ➔ 동부 ➔ 서귀포시 ➔ 서부' 순환 링 적용
     - 동부, 서부는 세부 거점 리스트 중 무작위(random.choice) 선택하여 다양성 확보
  3. 후보 리스트 검색: 
     - 각 일차별 앵커 반경 8km 내 '숙소, 관광지, 식당, 카페, 포토스팟' 검색
     - PostGIS 거리순 정렬 후 포토스팟은 5개, 나머지는 30개 1차 추출 (DB 부하 방지)
  4. 일차별 조건부 샘플링 및 중복 방지:
     - 이전 일차에 선택된 장소는 중복 제거(`used_place_ids`)
     - 포토스팟 데이터는 제한 없이 전체 리턴
     - 나머지 카테고리(숙소, 관광지, 식당, 카페)는 일자별 최대 6개씩 랜덤 선택
  5. 미매칭 키워드 조회: DB 반경 내 어떤 정보와도 매칭 안 된 키워드 반환 (PPL 노드 연동용)
────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router.protocol import QUST
    from .db_connector import DBConnector
    from .llm import LLM

from .db_connector import ALIAS_TABLE, SDB_TABLE


# ────────────────────────────────────────────────
# 조회 파라미터 상수
# ────────────────────────────────────────────────

CATEGORIES: tuple[str, ...] = ("숙소", "관광지", "식당", "카페", "포토스팟")
RADIUS_M: float = 8000.0
MAX_DAYS: int = 7

# DB에서 1차로 긁어올 카테고리별 최대 개수 제한
LIMIT_NORMAL: int = 30
LIMIT_PHOTO: int = 12

# 권역별 다중 앵커 좌표 (동부/서부는 세분화하여 다양성 확보)
REGION_CENTERS: dict[str, list[tuple[float, float]]] = {
    "제주도":   [(126.5312, 33.4996)],
    "제주시":   [(126.5312, 33.4996)],
    "동부":     [
        (126.6692, 33.5431),  # 조천/함덕 (북동)
        (126.8800, 33.4500),  # 성산 (정동)
        (126.8322, 33.3273)   # 표선 (남동)
    ],
    "서귀포시": [(126.5601, 33.2541)],
    "서부":     [
        (126.3200, 33.4600),  # 애월 (북서)
        (126.2390, 33.3940),  # 한림/협재 (정서)
        (126.2527, 33.2201)   # 대정/모슬포 (남서)
    ],
}

# 순환 링 순서
RING_ORDER = ["제주시", "동부", "서귀포시", "서부"]


# ────────────────────────────────────────────────
# LLM 프롬프트
# ────────────────────────────────────────────────

_INTENT_PROMPT = """다음 두 텍스트에서 region/days/keywords 세 가지를 추출하시오.

- region: 제주도 내의 시/읍/면/동/해변/관광 거점 등 구체적 지명 한 단어. 없거나 제주 외 지역이면 빈 문자열.
- days: 여행 총 일수(박수+1). "1박2일"→2, "2박3일"→3, "3박4일"→4. "M일"이면 M. 없으면 0.
- keywords: 사용자가 원하는 음식/메뉴/장소 특성/옵션 키워드 배열. 예: "흑돼지", "조용한", "오션뷰", "야경". 일반어("맛집", "카페")는 제외. 없으면 빈 배열.

두 텍스트에 모두 있으면 [사용자 메시지] 우선.

출력은 반드시 아래 JSON 한 줄. 코드블록·설명 금지.
{{"region": "지명 또는 빈문자열", "days": 정수, "keywords": ["...", ...]}}

[세션 주제]
{ssn_tpc}

[사용자 메시지]
{cc}
"""


# ────────────────────────────────────────────────
# SQL Queries
# ────────────────────────────────────────────────

_ANCHOR_QUERY = f"""
SELECT ST_X(geom) AS lon, ST_Y(geom) AS lat
FROM {SDB_TABLE}
WHERE name ILIKE %(pattern)s
  AND geom IS NOT NULL
LIMIT 1
"""

# [메인 검색]
_MAIN_QUERY = f"""
WITH matched_places AS (
    SELECT
        p.place_id, p.name, p.main_category, p.sub_category,
        p.address_road, p.region, p.region_depth_2, p.lat, p.lon, p.geom
    FROM {SDB_TABLE} p
    WHERE p.main_category = ANY(%(categories)s)
      AND p.geom IS NOT NULL
      AND ST_DWithin(
          p.geom,
          ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
          %(radius)s
      )
      AND (
          cardinality(%(keyword_patterns)s::text[]) = 0
          OR p.name ILIKE ANY(%(keyword_patterns)s)
          OR p.sub_category ILIKE ANY(%(keyword_patterns)s)
          OR EXISTS (
              SELECT 1 FROM {ALIAS_TABLE} a
              WHERE a.place_id = p.place_id
                AND a.alias ILIKE ANY(%(keyword_patterns)s)
          )
      )
),
ranked_places AS (
    SELECT
        m.*,
        (SELECT string_agg(a.alias, ', ') FROM {ALIAS_TABLE} a WHERE a.place_id = m.place_id) AS alias,
        ROW_NUMBER() OVER (
            PARTITION BY m.main_category
            ORDER BY ST_Distance(
                m.geom,
                ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
            ) ASC
        ) AS rn
    FROM matched_places m
)
SELECT *
FROM ranked_places
WHERE (main_category = '포토스팟' AND rn <= %(limit_photo)s)
   OR (main_category != '포토스팟' AND rn <= %(limit_normal)s)
ORDER BY main_category, rn
"""

# [미매칭 키워드 색인]
_UNMET_QUERY = f"""
SELECT k AS keyword
FROM unnest(%(keywords)s::text[]) AS k
WHERE NOT EXISTS (
    SELECT 1
    FROM {SDB_TABLE} p
    LEFT JOIN {ALIAS_TABLE} a ON p.place_id = a.place_id
    WHERE p.geom IS NOT NULL
      AND ST_DWithin(
            p.geom,
            ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
            %(radius)s
          )
      AND (
          p.name ILIKE '%%' || k || '%%'
          OR p.sub_category ILIKE '%%' || k || '%%'
          OR a.alias ILIKE '%%' || k || '%%'
      )
)
"""


# ────────────────────────────────────────────────
# 노드 클래스
# ────────────────────────────────────────────────

class SDB:

    def __init__(self, connector: "DBConnector", llm: "LLM") -> None:
        self._conn = connector
        self._llm = llm

    async def _extract_intent(
        self, ssn_tpc: str, cc: str
    ) -> tuple[str, int, list[str]]:
        """LLM 으로 (region, days, keywords) 추출. 실패 방어 로직 포함."""
        if not (ssn_tpc or cc):
            return ("", 0, [])
        prompt = _INTENT_PROMPT.format(ssn_tpc=ssn_tpc or "", cc=cc or "")
        raw = await self._llm.ask(prompt)
        
        if not raw or raw.startswith("ERROR:"):
            return ("", 0, [])

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").removeprefix("json").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ("", 0, [])

        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return ("", 0, [])

        try:
            region = str(data.get("region", "")).strip()
        except (ValueError, TypeError):
            region = ""

        try:
            days = max(0, int(data.get("days", 0)))
        except (ValueError, TypeError):
            days = 0

        try:
            raw_kws = data.get("keywords", []) or []
            keywords = [str(k).strip() for k in raw_kws if str(k).strip()]
        except (ValueError, TypeError):
            keywords = []

        return (region, days, keywords)

    def _resolve_anchors(self, days: int) -> list[tuple[float, float]]:
        """일수(days)를 기반으로 순환 링을 돌며 일차별 중심 위경도 리스트 반환"""
        if not days or days <= 0:
            return [REGION_CENTERS["제주시"][0]]
        
        anchors = []
        for i in range(days):
            region_name = RING_ORDER[i % len(RING_ORDER)]
            # 다중 앵커 후보군(동부, 서부 등)에서 무작위 거점 1개 선택
            chosen_anchor = random.choice(REGION_CENTERS[region_name])
            anchors.append(chosen_anchor)
            
        return anchors

    def _format_ppl_query(self, region: str, unmet: list[str]) -> str:
        if not unmet:
            return ""
        place = region or "제주도"
        items = ", ".join(unmet)
        return f"{place} 근처에서 {items} 관련 장소나 정보를 알려주세요."

    async def run(self, qust: "QUST") -> "QUST":
        from ..router.protocol import sDB_Item

        # 1. 의도 추출 및 일수 확정
        region, days, keywords = await self._extract_intent(qust.SSN_TPC, qust.CC)
        
        if qust.T_CD:
            days_effective = min(len(qust.T_CD), MAX_DAYS)
            anchors = self._resolve_anchors(days_effective)
        else:
            if days > 0:
                days_effective = min(days, MAX_DAYS)
                anchors = self._resolve_anchors(days_effective)
            else:
                days_effective = 1  # 일수가 없을 경우 기본 1일차 제주시 고정
                anchors = self._resolve_anchors(0)

        keyword_patterns = [f"%{k}%" for k in keywords]

        # 2. 일차별 데이터 구조 구축 및 조건부 샘플링
        structured_sdb = {}
        used_place_ids = set()  # 전체 일차 간 장소 중복 방지

        for day_idx, (lon, lat) in enumerate(anchors):
            day_num = day_idx + 1
            structured_sdb[day_num] = defaultdict(list)

            # 해당 일차 앵커에서 DB 조회
            db_rows = await self._conn.execute_raw(
                _MAIN_QUERY,
                {
                    "lon": lon,
                    "lat": lat,
                    "radius": RADIUS_M,
                    "categories": list(CATEGORIES),
                    "keyword_patterns": keyword_patterns,
                    "limit_normal": LIMIT_NORMAL,
                    "limit_photo": LIMIT_PHOTO,
                },
            )

            # 카테고리별 분류 및 중복 제거
            cat_groups = defaultdict(list)
            for row in db_rows:
                p_id = row["place_id"]
                if p_id not in used_place_ids:
                    cat_groups[row["main_category"]].append(row)
                    used_place_ids.add(p_id)

            # 카테고리별 요구사항 적용 (포토스팟 전체, 그 외 최대 6개 랜덤)
            for cat in CATEGORIES:
                rows = cat_groups.get(cat, [])
                if not rows:
                    continue
                
                if cat == "포토스팟":
                    sampled = rows
                else:
                    sampled = random.sample(rows, min(6, len(rows)))
                
                structured_sdb[day_num][cat] = [sDB_Item.from_dict(r) for r in sampled]

        # 3. QUST 객체에 결과 할당 (일차별 dict 구조)
        qust.sDB = dict(structured_sdb)
        qust.days = days_effective

        # 4. 미매칭 키워드 조회 (첫 번째 앵커 기준 대표 조회)
        if keywords and anchors:
            unmet_rows = await self._conn.execute_raw(
                _UNMET_QUERY,
                {
                    "lon": anchors[0][0],
                    "lat": anchors[0][1],
                    "radius": RADIUS_M,
                    "keywords": keywords,
                },
            )
            unmet = [r["keyword"] for r in unmet_rows]
            qust.PPL = self._format_ppl_query("제주도", unmet)
        else:
            qust.PPL = ""

        return qust