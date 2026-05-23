"""
[역할] sDB 조회 노드. 제주도 전용.

────────────────────────────────────────────────
흐름
────────────────────────────────────────────────
  qust.SSN_TPC, qust.CC  (자연어 텍스트)
        │
        ▼
  _extract_intent()  ← LLM 1회 호출, JSON 응답
        │             {"region": "...", "days": N, "keywords": [...]}
        ▼
  region(str) + days(int) + keywords(List[str])
        │
        ▼
  _resolve_anchor(region)  ← 3-tier
        │ Tier 1: REGION_CENTERS 직접 lookup
        │ Tier 2: places.name ILIKE 매칭
        │ Tier 3: random.choice(제주시, 서귀포시)
        ▼
  (lon, lat) 앵커
        │
        ▼
  메인 쿼리: 반경 8km, 카테고리별 거리순 (days × 3)개
            keywords 있으면 (name OR sub_category OR alias) ILIKE ANY 필터
        │
        ▼
  미매칭 쿼리 (keywords 있을 때만):
            반경 안에서 어떤 row 와도 매칭 안 된 키워드만 반환
        │
        ▼
  qust.sDB   ← 후보 리스트
  qust.days  ← 일수
  qust.PPL   ← DB 미매칭이 있을 때 "Perplexity 검색 요청 문장" 으로 채움
              (없으면 빈 문자열. ppl 노드가 이 문장을 받아 외부 검색 → 같은 PPL에 응답 덮어쓰기)
────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..router.protocol import QUST
    from .db_connector import DBConnector
    from .llm import LLM

from .db_connector import ALIAS_TABLE, SDB_TABLE


# ────────────────────────────────────────────────
# 조회 파라미터
# ────────────────────────────────────────────────

CATEGORIES: tuple[str, ...] = ("식당", "카페", "관광지", "포토스팟")
PER_DAY_PER_CATEGORY: int = 3
RADIUS_M: float = 8000.0
MAX_DAYS: int = 7   # LLM이 추출한 days 가 비정상적으로 크면 잘라 토큰/DB 부하 방지

# region 미추출 시 기본 앵커 후보. random.choice 로 하나 선택.
DEFAULT_CANDIDATES: tuple[tuple[float, float], ...] = (
    (126.5312, 33.4996),  # 제주시
    (126.5601, 33.2541),  # 서귀포시
)

# region 키워드 → 거리 기준점 (lon, lat). PostGIS 표준 (x=lon, y=lat).
REGION_CENTERS: dict[str, tuple[float, float]] = {
    # 광역
    "제주도":   (126.5312, 33.4996),
    "제주":     (126.5312, 33.4996),

    # 시 (region_depth_2)
    "제주시":   (126.5312, 33.4996),
    "서귀포시": (126.5601, 33.2541),
    "서귀포":   (126.5601, 33.2541),

    # 권역 (region)
    "북부":     (126.5312, 33.4996),
    "남부":     (126.5601, 33.2541),
    "동부":     (126.8800, 33.4500),
    "서부":     (126.2700, 33.4500),

    # 주요 거점
    "함덕":     (126.6700, 33.5430),
    "성산":     (126.9320, 33.4580),
    "우도":     (126.9530, 33.5060),
    "한라산":   (126.5300, 33.3617),
    "협재":     (126.2400, 33.3940),
    "중문":     (126.4080, 33.2470),
    "애월":     (126.3300, 33.4640),
}


# ────────────────────────────────────────────────
# LLM 프롬프트
# ────────────────────────────────────────────────

# 예시
_INTENT_PROMPT = """다음 두 텍스트에서 region/days/keywords 세 가지를 추출하시오.

- region: 제주도 내의 시/읍/면/동/해변/관광 거점 등 구체적 지명 한 단어. 없거나 제주 외 지역이면 빈 문자열.
- days: "N박M일", "M일" 등에서 일수(M)를 정수로. 없으면 0.
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
# SQL
# ────────────────────────────────────────────────

_ANCHOR_QUERY = f"""
SELECT lon, lat
FROM {SDB_TABLE}
WHERE name ILIKE %(pattern)s
LIMIT 1
"""

# 메인 검색: 키워드 있으면 name/sub_category/alias 중 하나라도 매칭되는 row 만.
_MAIN_QUERY = f"""
WITH ranked AS (
    SELECT
        p.name,
        p.address_road,
        p.main_category,
        ROW_NUMBER() OVER (
            PARTITION BY p.main_category
            ORDER BY ST_Distance(
                p.geom,
                ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
            ) ASC
        ) AS rn
    FROM {SDB_TABLE} p
    WHERE p.main_category = ANY(%(categories)s)
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
)
SELECT name, address_road, main_category
FROM ranked
WHERE rn <= %(top_k)s
ORDER BY main_category, rn
"""

# 반경 안에서 어떤 row 와도 매칭 안 된 키워드 반환.
_UNMET_QUERY = f"""
SELECT k AS keyword
FROM unnest(%(keywords)s::text[]) AS k
WHERE NOT EXISTS (
    SELECT 1
    FROM {SDB_TABLE} p
    LEFT JOIN {ALIAS_TABLE} a ON a.place_id = p.place_id
    WHERE ST_DWithin(
            p.geom,
            ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
            %(radius)s
          )
      AND (
            p.name         ILIKE '%%' || k || '%%'
         OR p.sub_category ILIKE '%%' || k || '%%'
         OR a.alias        ILIKE '%%' || k || '%%'
      )
)
"""


# ────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────

def _format_ppl_query(region: str, unmet: list[str]) -> str:
    """미매칭 키워드를 Perplexity 가 바로 받을 수 있는 자연어 문장으로 변환."""
    if not unmet:
        return ""
    place = region or "제주도"
    items = ", ".join(unmet)
    return f"{place} 근처에서 {items} 관련 장소나 정보를 알려주세요."


# ────────────────────────────────────────────────
# 노드
# ────────────────────────────────────────────────

class SDB:

    def __init__(self, connector: "DBConnector", llm: "LLM") -> None:
        self._conn = connector
        self._llm = llm

    async def _extract_intent(
        self, ssn_tpc: str, cc: str
    ) -> tuple[str, int, list[str]]:
        """LLM 으로 (region, days, keywords) 추출. 실패 → ("", 0, [])."""
        
        """
        [기능] LLM을 사용하여 사용자 텍스트에서 검색 파라미터 추출
        - JSON 형식을 강제하여 후속 로직에서 안전하게 파싱하도록 유도
        - LLM 응답이 불안정할 경우 빈 값 반환(Fallback)하여 시스템 전체 에러 방지
        """
        
        
        if not (ssn_tpc or cc):
            return ("", 0, [])
        prompt = _INTENT_PROMPT.format(ssn_tpc=ssn_tpc or "", cc=cc or "")
        raw = await self._llm.ask(prompt)
        if not raw or raw.startswith("ERROR:"):
            return ("", 0, [])

        # LLM 호출: 구조화된 데이터를 얻기 위한 추론 수행
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").removeprefix("json").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ("", 0, [])

        # JSON 유효성 검사 및 파싱
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return ("", 0, [])

        # 필드별 개별 방어 — 한 필드가 깨져도 나머지는 살림
        # (한 필드가 잘못되어도 전체가 죽지 않도록 개별 필드 예외 처리)
        
        try:
            region = str(data.get("region", "")).strip()
        except (ValueError, TypeError):
            region = ""

        try:
            days = max(0, int(data.get("days", 0)))
        except (ValueError, TypeError):
            days = 0

        
        # 키워드 배열 정제 (빈 문자열 제거)
        
        try:
            raw_kws = data.get("keywords", []) or []
            keywords = [str(k).strip() for k in raw_kws if str(k).strip()]
        except (ValueError, TypeError):
            keywords = []

        return (region, days, keywords)

    async def _resolve_anchor(self, region: str) -> tuple[float, float]:
        if region in REGION_CENTERS:
            return REGION_CENTERS[region]
        if region:
            rows = await self._conn.execute_raw(
                _ANCHOR_QUERY,
                {"pattern": f"%{region}%"},
            )
            if rows:
                return (float(rows[0]["lon"]), float(rows[0]["lat"]))
        return random.choice(DEFAULT_CANDIDATES)

    """
        [기능] SDB 노드의 메인 파이프라인
        1. 의도 추출 (Intent) -> 2. 위치 결정 (Anchor) -> 3. DB 검색 (Main Query) -> 4. 검색 보완 (Unmet Query)
    """
    
    async def run(self, qust: "QUST") -> "QUST":
        from ..router.protocol import sDB_Item

        # 1단계: 의도 파악
        region, days, keywords = await self._extract_intent(qust.SSN_TPC, qust.CC)
        days_effective = min(max(days, 1), MAX_DAYS)

        # 2단계: 좌표 결정 (PostGIS 쿼리를 위한 중심점 확보)
        lon, lat = await self._resolve_anchor(region)

        # 3단계: 주 쿼리 실행
        keyword_patterns = [f"%{k}%" for k in keywords]
        top_k = days_effective * PER_DAY_PER_CATEGORY

        rows = await self._conn.execute_raw(
            _MAIN_QUERY,
            {
                "lon": lon,
                "lat": lat,
                "radius": RADIUS_M,
                "top_k": top_k,
                "categories": list(CATEGORIES),
                "keyword_patterns": keyword_patterns,
            },
        )
        qust.sDB = [sDB_Item.from_dict(r) for r in rows]
        qust.days = days_effective

        # 4단계: 미매칭 키워드 분석 (검색 실패 시 외부 서비스 연동을 위한 Perplexity 쿼리 생성)
        if keywords:
            unmet_rows = await self._conn.execute_raw(
                _UNMET_QUERY,
                {
                    "lon": lon,
                    "lat": lat,
                    "radius": RADIUS_M,
                    "keywords": keywords,
                },
            )
            unmet = [r["keyword"] for r in unmet_rows]
            qust.PPL = _format_ppl_query(region, unmet)
        else:
            qust.PPL = ""

        return qust
