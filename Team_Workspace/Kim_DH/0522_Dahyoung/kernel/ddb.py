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
  qust.dDB : List[dDB_Item]   (forecast_date × location × forecast_time 조합, 최대 80개)

  dDB_Item 필드:
    location        장소                      "제주도" | "서귀포"
    forecast_date   예보 대상 날짜              "YYYYMMDD"
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

import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import aiohttp

if TYPE_CHECKING:
    from ..router.protocol import QUST
    from .db_connector import DBConnector

from .db_connector import DDB_TABLE


KST = ZoneInfo("Asia/Seoul")

FORECAST_TIMES = ("09", "12", "15", "18")
SHORT_MAX_DAY = 3
MID_MAX_DAY = 10

SHORT_ENDPOINT = (
    "http://apis.data.go.kr/1360000/"
    "VilageFcstInfoService_2.0/getVilageFcst"
)
MID_LAND_ENDPOINT = "http://apis.data.go.kr/1360000/MidFcstInfoService/getMidLandFcst"
MID_TEMP_ENDPOINT = "http://apis.data.go.kr/1360000/MidFcstInfoService/getMidTa"

JEJU_CITY = {
    "location": "제주시",
    "nx": 53,
    "ny": 38,
    "mid_reg_id": "11G00201",
    "lat": 33.4996,
    "lon": 126.5312,
}
SEOGWIPO = {
    "location": "서귀포시",
    "nx": 53,
    "ny": 33,
    "mid_reg_id": "11G00401",
    "lat": 33.2541,
    "lon": 126.5601,
}
LOCATIONS = (JEJU_CITY, SEOGWIPO)

SKY = {
    "1": "맑음",
    "3": "구름많음",
    "4": "흐림",
}
PTY = {
    "0": "",
    "1": "비",
    "2": "비/눈",
    "3": "눈",
    "4": "소나기",
    "5": "빗방울",
    "6": "빗방울/눈날림",
    "7": "눈날림",
}


class DDB:

    def __init__(self, connector: "DBConnector") -> None:
        self._conn = connector

    async def run(self, qust: "QUST") -> "QUST":
        from ..router.protocol import dDB_Item

        today = datetime.now(KST).date()
        dates = _resolve_dates(qust, today)
        if not dates:
            qust.dDB = []
            return qust

        results: list[dDB_Item] = []
        for target_date in dates[:MID_MAX_DAY + 1]:
            location = _resolve_location(qust, target_date)
            days_after = (target_date - today).days

            if days_after < 0 or days_after > MID_MAX_DAY:
                results.extend(_fallback_items(dDB_Item, target_date, location, "예보 범위 밖"))
                continue

            cached = await self._read_cache(dDB_Item, target_date, location)
            if cached:
                results.extend(cached)
                continue

            if days_after <= SHORT_MAX_DAY:
                items = await self._fetch_short(dDB_Item, target_date, location)
            else:
                items = await self._fetch_mid(dDB_Item, target_date, location, days_after)

            results.extend(items)
            await self._write_cache(target_date, location, items, days_after)

            if len(results) >= 80:
                break

        qust.dDB = results[:80]

        return qust

    async def _fetch_short(self, item_cls, target_date: date, location: dict) -> list:
        api_key = os.getenv("KMA_SHORT_API_KEY", "")
        if not api_key:
            return _fallback_items(item_cls, target_date, location, "단기예보 API 키 없음")

        base_date, base_time = _short_base_datetime(datetime.now(KST))
        params = {
            "serviceKey": api_key,
            "pageNo": "1",
            "numOfRows": "1000",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": str(location["nx"]),
            "ny": str(location["ny"]),
        }

        try:
            payload = await _get_json(SHORT_ENDPOINT, params)
            rows = _extract_items(payload)
        except Exception:
            return _fallback_items(item_cls, target_date, location, "단기예보 조회 실패")

        by_time: dict[str, dict[str, str]] = defaultdict(dict)
        target_ymd = target_date.strftime("%Y%m%d")
        for row in rows:
            if row.get("fcstDate") != target_ymd:
                continue
            hour = str(row.get("fcstTime", ""))[:2]
            if hour not in FORECAST_TIMES:
                continue
            by_time[hour][row.get("category", "")] = str(row.get("fcstValue", ""))

        return [
            _short_item(item_cls, target_date, location["location"], forecast_time, by_time[forecast_time])
            for forecast_time in FORECAST_TIMES
        ]

    async def _fetch_mid(self, item_cls, target_date: date, location: dict, days_after: int) -> list:
        api_key = os.getenv("KMA_MID_API_KEY", "")
        if not api_key:
            return _fallback_items(item_cls, target_date, location, "중기예보 API 키 없음")

        tm_fc = _mid_tm_fc(datetime.now(KST))
        base_params = {
            "serviceKey": api_key,
            "pageNo": "1",
            "numOfRows": "10",
            "dataType": "JSON",
            "regId": location["mid_reg_id"],
            "tmFc": tm_fc,
        }

        try:
            land_payload, temp_payload = await _get_mid_payloads(base_params)
            land = _first_item(land_payload)
            temp = _first_item(temp_payload)
        except Exception:
            return _fallback_items(item_cls, target_date, location, "중기예보 조회 실패")

        return [
            _mid_item(item_cls, target_date, location["location"], forecast_time, days_after, land, temp)
            for forecast_time in FORECAST_TIMES
        ]

    async def _read_cache(self, item_cls, target_date: date, location: dict) -> list:
        try:
            rows = await self._conn.select(
                DDB_TABLE,
                where={
                    "forecast_date": target_date.strftime("%Y%m%d"),
                    "location": location["location"],
                },
                limit=8,
            )
        except Exception:
            return []

        now = datetime.now(KST)
        valid = []
        for row in rows:
            expires_at = _parse_datetime(row.get("expires_at"))
            if expires_at and expires_at <= now:
                continue
            if row.get("forecast_time") in FORECAST_TIMES:
                valid.append(item_cls.from_dict(row))

        order = {t: i for i, t in enumerate(FORECAST_TIMES)}
        valid.sort(key=lambda item: order.get(item.forecast_time, 99))
        return valid if len(valid) >= len(FORECAST_TIMES) else []

    async def _write_cache(self, target_date: date, location: dict, items: list, days_after: int) -> None:
        ttl = timedelta(hours=2 if days_after <= SHORT_MAX_DAY else 12)
        now = datetime.now(KST)
        source_type = "short" if days_after <= SHORT_MAX_DAY else "mid"

        for item in items:
            data = item.to_dict() | {
                "forecast_date": target_date.strftime("%Y%m%d"),
                "source_type": source_type,
                "fetched_at": now,
                "expires_at": now + ttl,
            }
            try:
                await self._conn.insert(DDB_TABLE, data)
            except Exception:
                return


def _resolve_dates(qust: "QUST", today: date) -> list[date]:
    raw_dates: list[str] = []
    raw_dates.extend(qust.T_CD or [])

    for row in qust.T_PN or []:
        for item in row:
            item_date = getattr(item, "date", "")
            if item_date and item_date != "000000":
                raw_dates.append(item_date)

    raw_dates.extend(_extract_dates_from_text(" ".join([qust.CC or "", qust.SSN_TPC or ""]), today))

    parsed = [_parse_date(value, today) for value in raw_dates]
    unique = sorted({d for d in parsed if d is not None})
    return unique or [today]


def _resolve_location(qust: "QUST", target_date: date) -> dict:
    candidates: list[dict] = []

    target_yymmdd = target_date.strftime("%y%m%d")
    target_yyyymmdd = target_date.strftime("%Y%m%d")
    for row in qust.T_PN or []:
        for item in row:
            item_date = getattr(item, "date", "")
            if item_date and item_date not in {target_yymmdd, target_yyyymmdd, "000000"}:
                continue
            candidates.append(_location_from_place(getattr(item, "place", ""), getattr(item, "place_info", None)))

    for marker in qust.T_MK or []:
        candidates.append(_location_from_place("", getattr(marker, "place_info", None)))

    text_location = _location_from_text(" ".join([qust.CC or "", qust.SSN_TPC or ""]))
    if text_location:
        candidates.append(text_location)

    names = [c["location"] for c in candidates if c]
    if not names:
        return JEJU_CITY
    name = Counter(names).most_common(1)[0][0]
    return SEOGWIPO if name == SEOGWIPO["location"] else JEJU_CITY


def _location_from_place(place: str, place_info) -> dict:
    text = " ".join([
        place or "",
        getattr(place_info, "name", "") if place_info else "",
        getattr(place_info, "address_road", "") if place_info else "",
        getattr(place_info, "description", "") if place_info else "",
    ])
    location = _location_from_text(text)
    if location:
        return location

    lat = float(getattr(place_info, "lat", 0.0) or 0.0) if place_info else 0.0
    lon = float(getattr(place_info, "lon", 0.0) or 0.0) if place_info else 0.0
    if lat and lon:
        return min(LOCATIONS, key=lambda loc: _distance_km(lat, lon, loc["lat"], loc["lon"]))
    return JEJU_CITY


def _location_from_text(text: str) -> dict | None:
    if "서귀포" in text:
        return SEOGWIPO
    if "제주" in text:
        return JEJU_CITY
    return None


def _parse_date(value: str, today: date) -> date | None:
    value = str(value or "").strip()
    if not value or value == "000000":
        return None

    digits = re.sub(r"\D", "", value)
    try:
        if len(digits) == 8:
            return datetime.strptime(digits, "%Y%m%d").date()
        if len(digits) == 6:
            return datetime.strptime("20" + digits, "%Y%m%d").date()
        if len(digits) == 4:
            return date(today.year, int(digits[:2]), int(digits[2:]))
    except ValueError:
        return None
    return None


def _extract_dates_from_text(text: str, today: date) -> list[str]:
    values = re.findall(r"\b\d{4}[-./]?\d{1,2}[-./]?\d{1,2}\b", text)
    values.extend(re.findall(r"\b\d{1,2}[-./]\d{1,2}\b", text))

    if "오늘" in text:
        values.append(today.strftime("%Y%m%d"))
    if "내일" in text:
        values.append((today + timedelta(days=1)).strftime("%Y%m%d"))
    if "모레" in text:
        values.append((today + timedelta(days=2)).strftime("%Y%m%d"))
    return values


def _short_base_datetime(now: datetime) -> tuple[str, str]:
    base_times = (2, 5, 8, 11, 14, 17, 20, 23)
    safe_now = now - timedelta(minutes=20)
    hour = max((h for h in base_times if h <= safe_now.hour), default=23)
    base_day = safe_now.date() if hour != 23 or safe_now.hour >= 23 else safe_now.date() - timedelta(days=1)
    return base_day.strftime("%Y%m%d"), f"{hour:02d}00"


def _mid_tm_fc(now: datetime) -> str:
    safe_now = now - timedelta(minutes=20)
    if safe_now.hour >= 18:
        base = datetime.combine(safe_now.date(), time(18, 0), tzinfo=KST)
    elif safe_now.hour >= 6:
        base = datetime.combine(safe_now.date(), time(6, 0), tzinfo=KST)
    else:
        base = datetime.combine(safe_now.date() - timedelta(days=1), time(18, 0), tzinfo=KST)
    return base.strftime("%Y%m%d%H%M")


async def _get_json(url: str, params: dict[str, str]) -> dict:
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def _get_mid_payloads(params: dict[str, str]) -> tuple[dict, dict]:
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(MID_LAND_ENDPOINT, params=params) as land_resp:
            land_resp.raise_for_status()
            land = await land_resp.json(content_type=None)
        async with session.get(MID_TEMP_ENDPOINT, params=params) as temp_resp:
            temp_resp.raise_for_status()
            temp = await temp_resp.json(content_type=None)
    return land, temp


def _extract_items(payload: dict) -> list[dict]:
    items = payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    if isinstance(items, dict):
        return [items]
    return items or []


def _first_item(payload: dict) -> dict:
    rows = _extract_items(payload)
    return rows[0] if rows else {}


def _short_item(item_cls, target_date: date, location: str, forecast_time: str, values: dict[str, str]):
    sky = SKY.get(values.get("SKY", ""), "날씨 정보 없음")
    pty = PTY.get(values.get("PTY", ""), "")
    summary = pty or sky
    return item_cls(
        location=location,
        forecast_date=target_date.strftime("%Y%m%d"),
        forecast_time=forecast_time,
        summary=summary,
        rain_prob=_to_int(values.get("POP")),
        temperature=_to_float(values.get("TMP")),
        humidity=_to_int(values.get("REH")),
        wind_speed=_to_float(values.get("WSD")),
    )


def _mid_item(
    item_cls,
    target_date: date,
    location: str,
    forecast_time: str,
    days_after: int,
    land: dict,
    temp: dict,
):
    suffix = "Am" if forecast_time in {"09", "12"} else "Pm"
    wf_key = f"wf{days_after}{suffix}" if days_after <= 7 else f"wf{days_after}"
    rn_key = f"rnSt{days_after}{suffix}" if days_after <= 7 else f"rnSt{days_after}"

    summary = str(land.get(wf_key) or land.get(f"wf{days_after}") or "중기예보")
    rain_prob = _to_int(land.get(rn_key) or land.get(f"rnSt{days_after}"))
    temp_min = _to_float(temp.get(f"taMin{days_after}"))
    temp_max = _to_float(temp.get(f"taMax{days_after}"))
    temperature = _mid_temperature(forecast_time, temp_min, temp_max)

    return item_cls(
        location=location,
        forecast_date=target_date.strftime("%Y%m%d"),
        forecast_time=forecast_time,
        summary=summary,
        rain_prob=rain_prob,
        temperature=temperature,
        humidity=0,
        wind_speed=0.0,
    )


def _fallback_items(item_cls, target_date: date, location: dict, reason: str) -> list:
    return [
        item_cls(
            location=location["location"],
            forecast_date=target_date.strftime("%Y%m%d"),
            forecast_time=forecast_time,
            summary=reason,
            rain_prob=0,
            temperature=0.0,
            humidity=0,
            wind_speed=0.0,
        )
        for forecast_time in FORECAST_TIMES
    ]


def _mid_temperature(forecast_time: str, temp_min: float, temp_max: float) -> float:
    if not temp_min and not temp_max:
        return 0.0
    if forecast_time == "09":
        return temp_min
    if forecast_time == "15":
        return temp_max
    return round((temp_min + temp_max) / 2, 1)


def _to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=KST)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))
