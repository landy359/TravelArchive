import re
from typing import Any, Dict, List, Optional


class TripSelectWidget:
    """T_SL: str — 현재 선택된 여행지/옵션 (공백=없음)."""

    _REDIS_KEY = "widget:t_sl"
    _EMPTY_VALUES = {"", "none", "null", "없음", "선택지 없음"}

    def __init__(self) -> None:
        self._state: str = ""

    @classmethod
    def _normalize(cls, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        normalized = re.sub(r"\s+", " ", value).strip()
        return "" if normalized.lower() in cls._EMPTY_VALUES else normalized

    @staticmethod
    def _split_option_text(text: str) -> tuple[str, str]:
        for separator in (" - ", " – ", " — ", ": "):
            if separator in text:
                title, description = text.split(separator, 1)
                return title.strip(), description.strip()
        return text.strip(), ""

    @classmethod
    def _parse_options(cls, value: Any) -> List[Dict[str, str]]:
        text = cls._normalize(value)
        if not text:
            return []

        pattern = re.compile(
            r"(?:^|[\|\n;/])\s*"
            r"(?P<key>[AaBb])\s*(?:안)?\s*[:：\)\].\-]?\s*"
            r"(?P<body>.*?)"
            r"(?=(?:[\|\n;/]\s*[AaBb]\s*(?:안)?\s*[:：\)\].\-]?)|$)",
            re.S,
        )
        options: Dict[str, Dict[str, str]] = {}
        for match in pattern.finditer(text):
            key = match.group("key").upper()
            body = re.sub(r"\s+", " ", match.group("body")).strip(" -–—:：")
            if key not in {"A", "B"} or not body:
                continue
            title, description = cls._split_option_text(body)
            options[key] = {
                "key": key,
                "label": f"{key}안",
                "title": title,
                "description": description,
                "value": f"{key}안: {body}",
            }

        return [options[key] for key in ("A", "B") if key in options]

    @classmethod
    def format_for_front(cls, value: Any) -> Dict[str, Any]:
        raw = cls._normalize(value)
        options = cls._parse_options(raw)
        visible = len(options) == 2
        return {
            "visible": visible,
            "raw": raw if visible else "",
            "options": options if visible else [],
        }

    # ── LLM 경로 ──────────────────────────────────────────────────

    def get_for_llm(self) -> str:
        return self._state

    def set_for_llm(self, value: str) -> None:
        self._state = self._normalize(value)

    # ── 프론트 경로 ────────────────────────────────────────────────
    # LLM 경로는 기존 프로토콜 호환을 위해 str을 유지하고,
    # 프론트 경로는 선택 카드 표출용 dict로 변환한다.

    def get_for_front(self) -> Dict[str, Any]:
        return self.format_for_front(self._state)

    def set_for_front(self, value: str) -> None:
        self._state = self._normalize(value)

    # ── Redis 경로 ─────────────────────────────────────────────────

    @staticmethod
    async def save_to_redis(scope_key: str, redis, value: str) -> None:
        from ...memory.constants import DATA_TTL
        await redis.set_json(f"{scope_key}:{TripSelectWidget._REDIS_KEY}", TripSelectWidget._normalize(value), DATA_TTL)

    @staticmethod
    async def load_from_redis(scope_key: str, redis) -> str:
        data: Optional[str] = await redis.get_json(f"{scope_key}:{TripSelectWidget._REDIS_KEY}")
        return data if isinstance(data, str) else ""
