"""
protocol.py
라우터 내부 JSON 포맷 선언

하얀 화살표(JSON 직렬화) 구간:
  Port1  → Core  : PC1
  Core  ↔ Port2  : PC2
  Core  ↔ Port3  : PC3
  Port3 → LLM    : QUST
  LLM   → Port3  : PC3 (JSON 파싱 후 직접 반환)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


# ────────────────────────────────────────────────────
# 공통 중첩 타입
# ────────────────────────────────────────────────────

@dataclass
class PlaceInfo:
    name:         str   = ""
    address_road: str   = ""
    lat:          float = 0.0
    lng:          float = 0.0
    description:  str   = ""
    category:     str   = ""

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "address_road": self.address_road,
            "lat":          self.lat,
            "lng":          self.lng,
            "description":  self.description,
            "category":     self.category,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlaceInfo:
        return cls(
            name=d.get("name", ""),
            address_road=d.get("address_road", ""),
            lat=float(d.get("lat", 0.0)),
            lng=float(d.get("lng", 0.0)),
            description=d.get("description", ""),
            category=d.get("category", ""),
        )


@dataclass
class T_MK_Item:
    """T_MK : JSON[] = { STR, PLACE_INFO }"""
    marker_id:  str       = ""
    place_info: PlaceInfo = field(default_factory=PlaceInfo)

    def to_dict(self) -> dict:
        return {
            "marker_id":  self.marker_id,
            "place_info": self.place_info.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> T_MK_Item:
        return cls(
            marker_id=d.get("marker_id", ""),
            place_info=PlaceInfo.from_dict(d.get("place_info", {})),
        )


@dataclass
class T_PN_Item:
    """T_PN : JSON[7][10] = { 날짜, 순서, 장소, 장소정보 }"""
    date:       str       = "000000"   # YYMMDD
    order:      int       = 0
    place:      str       = ""
    place_info: PlaceInfo = field(default_factory=PlaceInfo)

    def to_dict(self) -> dict:
        return {
            "date":       self.date,
            "order":      self.order,
            "place":      self.place,
            "place_info": self.place_info.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> T_PN_Item:
        return cls(
            date=d.get("date", "000000"),
            order=int(d.get("order", 0)),
            place=d.get("place", ""),
            place_info=PlaceInfo.from_dict(d.get("place_info", {})),
        )


@dataclass
class sDB_Item:
    """sDB : 정적 장소 DB 레코드"""
    place_id:       str   = ""
    name:           str   = ""
    main_category:  str   = ""
    sub_category:   str   = ""
    address_road:   str   = ""
    lat:            float = 0.0
    lon:            float = 0.0
    region:         str   = ""
    region_depth_2: str   = ""
    alias:          str   = ""

    def to_dict(self) -> dict:
        return {
            "place_id":       self.place_id,
            "name":           self.name,
            "main_category":  self.main_category,
            "sub_category":   self.sub_category,
            "address_road":   self.address_road,
            "lat":            self.lat,
            "lon":            self.lon,
            "region":         self.region,
            "region_depth_2": self.region_depth_2,
            "alias":          self.alias,
        }

    @classmethod
    def from_dict(cls, d: dict) -> sDB_Item:
        return cls(
            place_id=d.get("place_id", ""),
            name=d.get("name", ""),
            main_category=d.get("main_category", ""),
            sub_category=d.get("sub_category", ""),
            address_road=d.get("address_road", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            region=d.get("region", ""),
            region_depth_2=d.get("region_depth_2", ""),
            alias=d.get("alias", ""),
        )


@dataclass
class dDB_Item:
    """dDB : 동적 날씨 API 레코드"""
    location:      str   = ""
    forecast_time: str   = ""   # "09" | "12" | "15" | "18"
    summary:       str   = ""
    rain_prob:     int   = 0    # 0~100
    temperature:   float = 0.0
    humidity:      int   = 0    # 0~100
    wind_speed:    float = 0.0

    def to_dict(self) -> dict:
        return {
            "location":      self.location,
            "forecast_time": self.forecast_time,
            "summary":       self.summary,
            "rain_prob":     self.rain_prob,
            "temperature":   self.temperature,
            "humidity":      self.humidity,
            "wind_speed":    self.wind_speed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> dDB_Item:
        return cls(
            location=d.get("location", ""),
            forecast_time=d.get("forecast_time", ""),
            summary=d.get("summary", ""),
            rain_prob=int(d.get("rain_prob", 0)),
            temperature=float(d.get("temperature", 0.0)),
            humidity=int(d.get("humidity", 0)),
            wind_speed=float(d.get("wind_speed", 0.0)),
        )


# ────────────────────────────────────────────────────
# 내부 유틸
# ────────────────────────────────────────────────────

def _mk_to_list(items: List[T_MK_Item]) -> list:
    return [i.to_dict() for i in items]

def _mk_from_list(lst: list) -> List[T_MK_Item]:
    return [T_MK_Item.from_dict(i) for i in lst]

def _pn_to_list(matrix: List[List[T_PN_Item]]) -> list:
    return [[item.to_dict() for item in row] for row in matrix]

def _pn_from_list(lst: list) -> List[List[T_PN_Item]]:
    return [[T_PN_Item.from_dict(item) for item in row] for row in lst]


# ────────────────────────────────────────────────────
# PC1  (Port1 → Core, 단방향)
# ────────────────────────────────────────────────────

@dataclass
class PC1:
    USR_ANAL: str = ""   # 유저 성향 분석 정보
    SSN_TPC:  str = ""   # 세션 주제
    SSN_PCL:  str = ""   # 과거 대화 기록

    def to_dict(self) -> dict:
        return {
            "USR_ANAL": self.USR_ANAL,
            "SSN_TPC":  self.SSN_TPC,
            "SSN_PCL":  self.SSN_PCL,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PC1:
        return cls(
            USR_ANAL=d.get("USR_ANAL", ""),
            SSN_TPC=d.get("SSN_TPC", ""),
            SSN_PCL=d.get("SSN_PCL", ""),
        )


# ────────────────────────────────────────────────────
# PC2  (Port2 ↔ Core, 양방향)
# ────────────────────────────────────────────────────

@dataclass
class PC2:
    CC:   str                    = ""                      # 현재 대화 / 쿼리
    T_SL: str                    = ""                      # 선택지 (공백=없음)
    T_CD: List[str]              = field(default_factory=list)  # 날짜 범위 ["YYMMDD", ...]
    T_MP: List[str]              = field(default_factory=list)  # 지도 폴리곤 노드
    T_MK: List[T_MK_Item]       = field(default_factory=list)  # 마커 목록
    T_PN: List[List[T_PN_Item]] = field(default_factory=list)  # 일정표 [day][order]

    def to_dict(self) -> dict:
        return {
            "CC":   self.CC,
            "T_SL": self.T_SL,
            "T_CD": self.T_CD,
            "T_MP": self.T_MP,
            "T_MK": _mk_to_list(self.T_MK),
            "T_PN": _pn_to_list(self.T_PN),
        }

    @classmethod
    def from_dict(cls, d: dict) -> PC2:
        return cls(
            CC=d.get("CC", ""),
            T_SL=d.get("T_SL", ""),
            T_CD=d.get("T_CD", []),
            T_MP=d.get("T_MP", []),
            T_MK=_mk_from_list(d.get("T_MK", [])),
            T_PN=_pn_from_list(d.get("T_PN", [])),
        )


# ────────────────────────────────────────────────────
# PC3  (Core ↔ Port3, 양방향)
# PC1 + PC2 합산 구조
# ────────────────────────────────────────────────────

@dataclass
class PC3:
    # PC1 필드
    USR_ANAL: str = ""
    SSN_TPC:  str = ""
    SSN_PCL:  str = ""
    # PC2 필드
    CC:   str                             = ""
    T_SL: str                             = ""
    # None = LLM이 해당 필드를 생략함 (keep old). [] = 명시적 초기화.
    T_CD: Optional[List[str]]              = field(default=None)
    T_MP: Optional[List[str]]              = field(default=None)
    T_MK: Optional[List[T_MK_Item]]       = field(default=None)
    T_PN: Optional[List[List[T_PN_Item]]] = field(default=None)

    def to_dict(self) -> dict:
        return {
            "USR_ANAL": self.USR_ANAL,
            "SSN_TPC":  self.SSN_TPC,
            "SSN_PCL":  self.SSN_PCL,
            "CC":       self.CC,
            "T_SL":     self.T_SL,
            "T_CD":     self.T_CD or [],
            "T_MP":     self.T_MP or [],
            "T_MK":     _mk_to_list(self.T_MK or []),
            "T_PN":     _pn_to_list(self.T_PN or []),
        }

    @classmethod
    def from_dict(cls, d: dict) -> PC3:
        return cls(
            USR_ANAL=d.get("USR_ANAL", ""),
            SSN_TPC=d.get("SSN_TPC", ""),
            SSN_PCL=d.get("SSN_PCL", ""),
            CC=d.get("CC", ""),
            T_SL=d.get("T_SL", ""),
            T_CD=d.get("T_CD", []),
            T_MP=d.get("T_MP", []),
            T_MK=_mk_from_list(d.get("T_MK", [])),
            T_PN=_pn_from_list(d.get("T_PN", [])),
        )

    def to_pc2(self) -> PC2:
        """PC3에서 PC2 필드만 추출 (Core split 시 사용)"""
        return PC2(
            CC=self.CC,
            T_SL=self.T_SL,
            T_CD=self.T_CD or [],
            T_MP=self.T_MP or [],
            T_MK=self.T_MK or [],
            T_PN=self.T_PN or [],
        )


# ────────────────────────────────────────────────────
# QUST  (Port3 → LLM, 단방향)
# PC3 + sDB/dDB/PPL
# ────────────────────────────────────────────────────

@dataclass
class QUST:
    # PC3 필드 전체
    USR_ANAL: str = ""
    SSN_TPC:  str = ""
    SSN_PCL:  str = ""
    CC:   str                    = ""
    T_SL: str                    = ""
    T_CD: List[str]              = field(default_factory=list)
    T_MP: List[str]              = field(default_factory=list)
    T_MK: List[T_MK_Item]       = field(default_factory=list)
    T_PN: List[List[T_PN_Item]] = field(default_factory=list)
    # Kernel 조회 결과
    sDB:  List[sDB_Item]        = field(default_factory=list)
    dDB:  List[dDB_Item]        = field(default_factory=list)
    PPL:  str                   = ""

    def to_dict(self) -> dict:
        return {
            "USR_ANAL": self.USR_ANAL,
            "SSN_TPC":  self.SSN_TPC,
            "SSN_PCL":  self.SSN_PCL,
            "CC":       self.CC,
            "T_SL":     self.T_SL,
            "T_CD":     self.T_CD,
            "T_MP":     self.T_MP,
            "T_MK":     _mk_to_list(self.T_MK),
            "T_PN":     _pn_to_list(self.T_PN),
            "sDB":      [i.to_dict() for i in self.sDB],
            "dDB":      [i.to_dict() for i in self.dDB],
            "PPL":      self.PPL,
        }


