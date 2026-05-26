from datetime import date, timedelta
import re
from typing import Any, List, Optional


class TripClanderWidget:
    """T_CD: List[str] — 여행 날짜 범위 ["YYMMDD", ...]."""

    _REDIS_KEY = "widget:t_cd"

    def __init__(self) -> None:
        self._state: List[str] = []

    @staticmethod
    def _normalize_dates(value: Any) -> List[str]:
        today = date.today()
        raw_items = TripClanderWidget._flatten_input(value)
        text_parts: List[str] = []
        parsed_dates: List[date] = []

        for item in raw_items:
            if isinstance(item, date):
                parsed_dates.append(item)
                continue

            if not isinstance(item, str):
                continue

            text = item.strip()
            if not text:
                continue

            text_parts.append(text)
            parsed_dates.extend(TripClanderWidget._extract_dates(text, today.year))

        parsed_dates = TripClanderWidget._unique_dates(parsed_dates)
        if not parsed_dates:
            return []

        nights = TripClanderWidget._extract_nights(" ".join(text_parts))

        if len(parsed_dates) == 1:
            start = parsed_dates[0]
            end = start + timedelta(days=nights) if nights is not None else start
            return [TripClanderWidget._format_date(start), TripClanderWidget._format_date(end)]

        start = min(parsed_dates)
        end = max(parsed_dates)
        return [TripClanderWidget._format_date(start), TripClanderWidget._format_date(end)]

    @staticmethod
    def _flatten_input(value: Any) -> List[Any]:
        if value is None:
            return []

        if isinstance(value, dict):
            flattened: List[Any] = []
            for key in (
                "start",
                "start_date",
                "from",
                "begin",
                "end",
                "end_date",
                "to",
                "return_date",
                "dates",
                "range",
                "t_cd",
                "T_CD",
            ):
                if key in value:
                    flattened.extend(TripClanderWidget._flatten_input(value[key]))
            return flattened

        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(TripClanderWidget._flatten_input(item))
            return flattened

        return [value]

    @staticmethod
    def _extract_dates(text: str, current_year: int) -> List[date]:
        results: List[date] = []
        patterns = (
            re.compile(
                "(?P<year>\\d{4})\\s*(?:[-./]|\\uB144)\\s*"
                "(?P<month>\\d{1,2})\\s*(?:[-./]|\\uC6D4)\\s*"
                "(?P<day>\\d{1,2})\\s*\\uC77C?"
            ),
            re.compile(r"\b(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})\b"),
            re.compile(r"\b(?P<year>\d{2})(?P<month>\d{2})(?P<day>\d{2})\b"),
            re.compile("(?<!\\d)(?P<month>\\d{1,2})\\s*\\uC6D4\\s*(?P<day>\\d{1,2})\\s*\\uC77C?"),
        )

        for pattern in patterns:
            for match in pattern.finditer(text):
                year_text = match.groupdict().get("year")
                year = TripClanderWidget._normalize_year(year_text, current_year)
                month = int(match.group("month"))
                day = int(match.group("day"))
                parsed = TripClanderWidget._build_date(year, month, day)
                if parsed is not None:
                    results.append(parsed)

        return results

    @staticmethod
    def _extract_nights(text: str) -> Optional[int]:
        match = re.search("(?P<nights>\\d+)\\s*\\uBC15(?:\\s*\\d+\\s*\\uC77C)?", text)
        if not match:
            return None
        return int(match.group("nights"))

    @staticmethod
    def _normalize_year(year_text: Optional[str], current_year: int) -> int:
        if not year_text:
            return current_year
        if len(year_text) == 2:
            return 2000 + int(year_text)
        return int(year_text)

    @staticmethod
    def _build_date(year: int, month: int, day: int) -> Optional[date]:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _unique_dates(values: List[date]) -> List[date]:
        seen = set()
        unique: List[date] = []
        for value in values:
            key = value.toordinal()
            if key in seen:
                continue
            seen.add(key)
            unique.append(value)
        return unique

    @staticmethod
    def _format_date(value: date) -> str:
        return value.strftime("%y%m%d")

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> List[str]:
        return list(self._state)

    def set_for_llm(self, value: Any) -> None:
        self._state = self._normalize_dates(value)

    # ── 프론트 경로 ────────────────────────────────────────────────
    # T_CD 는 LLM·프론트 형상이 동일(List[str])하므로 별도 변환 불필요.
    # 캘린더 위젯 표출 형식(예: "YYMMDD" → datetime 객체 등)이 달라질 경우
    # 아래 두 메서드에서 변환 구현.

    def get_for_front(self) -> List[str]:
        return list(self._state)

    def set_for_front(self, value: Any) -> None:
        self._state = self._normalize_dates(value)

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(session_id: str, redis, value: Any) -> None:
        from ...memory.constants import DATA_TTL
        normalized = TripClanderWidget._normalize_dates(value)
        await redis.set_json(f"session:{session_id}:{TripClanderWidget._REDIS_KEY}", normalized, DATA_TTL)

    @staticmethod
    async def load_from_redis(session_id: str, redis) -> List[str]:
        data: Optional[list] = await redis.get_json(f"session:{session_id}:{TripClanderWidget._REDIS_KEY}")
        return TripClanderWidget._normalize_dates(data)
