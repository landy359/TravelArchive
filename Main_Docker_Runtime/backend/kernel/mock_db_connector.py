"""
CSV 기반 MockDBConnector — PostGIS 없이 sdb.py를 돌리기 위한 목업.
DB_Places_Master_Final.csv 와 DB_Place_Aliases_Finalv.csv 를 메모리에 올려
execute_raw 호출을 Python으로 처리한다.

사용법:
    from backend.kernel.mock_db_connector import MockDBConnector
    from backend.kernel.llm import LLM
    from backend.kernel.sdb import SDB

    sdb = SDB(MockDBConnector(), LLM())
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

_SEEDS_DIR = Path(__file__).parents[2] / "db" / "seeds"
_PLACES_CSV = _SEEDS_DIR / "DB_Places_Master_Final.csv"
_ALIASES_CSV = _SEEDS_DIR / "DB_Place_Aliases_Finalv.csv"


# ────────────────────────────────────────────────
# 공간 유틸
# ────────────────────────────────────────────────

def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _ilike(text: str, pattern: str) -> bool:
    """ILIKE % 와일드카드 매칭 (대소문자 무시)."""
    t = (text or "").lower()
    p = pattern.lower()
    if p.startswith("%") and p.endswith("%"):
        return p[1:-1] in t
    if p.startswith("%"):
        return t.endswith(p[1:])
    if p.endswith("%"):
        return t.startswith(p[:-1])
    return t == p


def _ilike_any(text: str, patterns: list[str]) -> bool:
    return any(_ilike(text, p) for p in patterns)


# ────────────────────────────────────────────────
# MockDBConnector
# ────────────────────────────────────────────────

class MockDBConnector:

    def __init__(
        self,
        places_csv: Path | None = None,
        aliases_csv: Path | None = None,
    ) -> None:
        self._places = self._load_places(places_csv or _PLACES_CSV)
        self._aliases = self._load_aliases(aliases_csv or _ALIASES_CSV)

    # ── 로더 ────────────────────────────────────

    @staticmethod
    def _load_places(path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["lat"] = float(r["lat"]) if r.get("lat") else 0.0
            r["lon"] = float(r["lon"]) if r.get("lon") else 0.0
        return rows

    @staticmethod
    def _load_aliases(path: Path) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                result.setdefault(row["place_id"], []).append(row["alias"])
        return result

    # ── 공개 API (sdb.py 가 쓰는 것만 구현) ────

    async def execute_raw(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        p = params or {}
        if "unnest" in query:
            return self._query_unmet(p)
        if "ROW_NUMBER" in query:
            return self._query_main(p)
        return self._query_anchor(p)

    def lookup_by_name(self, name: str) -> dict | None:
        """장소명으로 CSV에서 실제 좌표/주소를 조회. 완전 일치 우선, 없으면 부분 일치."""
        nl = name.lower().strip()
        for row in self._places:
            if row["name"].lower() == nl:
                return row
        for row in self._places:
            rn = row["name"].lower()
            if nl in rn or rn in nl:
                return row
        return None

    # ── 쿼리 핸들러 ─────────────────────────────

    def _query_anchor(self, p: dict) -> list[dict]:
        """_ANCHOR_QUERY: name ILIKE pattern → {lon, lat}."""
        pattern = p.get("pattern", "")
        for row in self._places:
            if _ilike(row["name"], pattern):
                return [{"lon": row["lon"], "lat": row["lat"]}]
        return []

    def _query_main(self, p: dict) -> list[dict]:
        """_MAIN_QUERY: 반경+카테고리+키워드 필터 → 카테고리별 거리순 top_k."""
        lon: float = float(p["lon"])
        lat: float = float(p["lat"])
        radius: float = float(p["radius"])
        top_k: int = int(p["top_k"])
        categories: list[str] = list(p.get("categories") or [])
        kw_patterns: list[str] = list(p.get("keyword_patterns") or [])

        # 1. 반경 필터 + 카테고리 필터
        candidates = []
        for row in self._places:
            if row["main_category"] not in categories:
                continue
            dist = _haversine_m(lon, lat, row["lon"], row["lat"])
            if dist > radius:
                continue
            candidates.append((dist, row))

        # 2. 키워드 필터 (패턴 있을 때만)
        if kw_patterns:
            filtered = []
            for dist, row in candidates:
                aliases = self._aliases.get(row["place_id"], [])
                if (
                    _ilike_any(row["name"], kw_patterns)
                    or _ilike_any(row.get("sub_category", ""), kw_patterns)
                    or any(_ilike_any(a, kw_patterns) for a in aliases)
                ):
                    filtered.append((dist, row))
            candidates = filtered

        # 3. 카테고리별 거리순 정렬 → top_k
        by_cat: dict[str, list[tuple[float, dict]]] = {}
        for dist, row in candidates:
            by_cat.setdefault(row["main_category"], []).append((dist, row))
        for cat in by_cat:
            by_cat[cat].sort(key=lambda x: x[0])

        results = []
        for cat in sorted(by_cat):
            for dist, row in by_cat[cat][:top_k]:
                aliases = self._aliases.get(row["place_id"], [])
                results.append({
                    "name":           row["name"],
                    "address_road":   row.get("address_road", ""),
                    "main_category":  row["main_category"],
                    "sub_category":   row.get("sub_category", ""),
                    "place_id":       row.get("place_id", ""),
                    "lat":            row["lat"],
                    "lon":            row["lon"],
                    "region":         row.get("region", ""),
                    "region_depth_2": row.get("region_depth_2", ""),
                    "alias":          ", ".join(aliases),
                })
        return results

    def _query_unmet(self, p: dict) -> list[dict]:
        """_UNMET_QUERY: 반경 내에서 매칭 안 된 키워드 반환."""
        lon: float = float(p["lon"])
        lat: float = float(p["lat"])
        radius: float = float(p["radius"])
        keywords: list[str] = list(p.get("keywords") or [])

        # 반경 내 후보만 추려서 비교
        nearby = [
            row for row in self._places
            if _haversine_m(lon, lat, row["lon"], row["lat"]) <= radius
        ]

        unmet = []
        for kw in keywords:
            pattern = f"%{kw}%"
            matched = False
            for row in nearby:
                aliases = self._aliases.get(row["place_id"], [])
                if (
                    _ilike(row["name"], pattern)
                    or _ilike(row.get("sub_category", ""), pattern)
                    or any(_ilike(a, pattern) for a in aliases)
                ):
                    matched = True
                    break
            if not matched:
                unmet.append({"keyword": kw})
        return unmet
