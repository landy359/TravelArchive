"""
[역할] Perplexity 검색 노드.
       QUST를 받아 PPL·route_keywords 필드를 채운 뒤 반환한다.

────────────────────────────────────────────────
입력 (QUST에서 읽는 필드)
────────────────────────────────────────────────
  qust.SSN_TPC  : 세션 주제 ("제주도 3박4일 여행" 등)
  qust.T_CD     : 날짜 범위 ["YYMMDD", ...]
  qust.CC       : 현재 사용자 메시지
  qust.kw_hint  : 사용자 선호 키워드 힌트 (keyword_scorer에서 주입)

────────────────────────────────────────────────
출력 (QUST에 채우는 필드)
────────────────────────────────────────────────
  qust.PPL           : str  — Perplexity가 반환한 경로 후보 텍스트 (plain text)
  qust.route_keywords: dict — {route_num: {name: str, keywords: list[str]}}
────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Optional

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from ..router.protocol import QUST


# llm.py와 동일한 모듈 레벨 캐시 — api_key별로 클라이언트 하나만 유지
_client_cache: dict[str, AsyncOpenAI] = {}


def _get_client(api_key: str) -> AsyncOpenAI:
    if api_key not in _client_cache:
        _client_cache[api_key] = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
        )
    return _client_cache[api_key]


# 실제 여행자들이 비슷한 날씨·장소 조건에서 선택한 경로를 검색하는 프롬프트
_SYSTEM_PROMPT = """
You are a travel route research assistant with access to real-time web information.

Task: given a list of places and weather conditions, find what routes real travelers
commonly take or recommend under similar circumstances.

Output rules:
- Plain text only
- No markdown formatting
- No citation numbers like [1] or [2]
- No URLs or links
- List exactly 5 route candidates, numbered 1 to 5
- Each candidate: route name followed by colon, key stops in order, one sentence on why travelers choose it
- After the description, add a keyword line: "키워드: kw1, kw2, kw3, kw4, kw5" (exactly 5 Korean keywords per route)
- If preferred keywords are provided, include at least 2 of them per candidate

Focus on:
- Actual traveler behavior (blogs, reviews, community posts) for the region and season
- How weather conditions affect which routes people prefer
- Variety across the 5 candidates (e.g. rainy-day indoor heavy vs clear-day outdoor)

Answer in Korean.
""".strip()

# 경로별 키워드 파싱 패턴 (모듈 로드 시 컴파일)
_RE_ROUTE_BLOCK = re.compile(r'^\d+\.', re.MULTILINE)
_RE_ROUTE_NAME  = re.compile(r'^\d+\.\s+(.+?)[:：]')
_RE_KEYWORDS    = re.compile(r'키워드:\s*(.+)')

_USER_PREFIX = "다음 장소 목록과 날씨 데이터를 바탕으로 실제 여행자들이 선택하는 경로 후보를 5개 뽑아라."

# _clean에서 사용하는 패턴 — 모듈 로드 시 한 번만 컴파일
_RE_CITATION  = re.compile(r"\[\d+(?:,\s*\d+)*\]")
_RE_BOLD      = re.compile(r"\*\*(.*?)\*\*")
_RE_ITALIC    = re.compile(r"\*(.*?)\*")
_RE_CODE      = re.compile(r"`(.*?)`")
_RE_URL       = re.compile(r"https?://\S+")
_RE_META      = re.compile(
    r"(?:According to|Search results|Sources indicate|Based on the search results).*?:",
    re.IGNORECASE,
)
_RE_BLANK     = re.compile(r"\n{3,}")


class PPL:

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "sonar",
        temperature: float = 0.3,  # 경로 다양성을 위해 0.2 → 0.3
    ) -> None:
        self._api_key = api_key or os.getenv("PERPLEXITY_API_KEY") or ""
        self._model = model
        self._temperature = temperature

    def _build_prompt(self, qust: "QUST") -> str:
        parts = [_USER_PREFIX]

        if qust.SSN_TPC:
            parts.append(f"여행 주제: {qust.SSN_TPC}")

        if qust.T_CD:
            parts.append(f"여행 날짜: {', '.join(qust.T_CD)}")

        if qust.CC:
            parts.append(f"사용자 요청: {qust.CC}")

        if qust.kw_hint:
            parts.append(f"선호 키워드 (각 경로에 가능한 한 포함): {', '.join(qust.kw_hint)}")

        # T_MK — 관심 마커 (PC3에서 사용자가 찍은 장소)
        if qust.T_MK:
            names = [mk.place_info.name for mk in qust.T_MK if mk.place_info.name]
            if names:
                parts.append(f"관심 장소: {', '.join(names)}")

        # T_PN — 기존 일정 (PC3에서 넘어온 일정표)
        if qust.T_PN:
            scheduled = [item.place for day in qust.T_PN for item in day if item.place]
            if scheduled:
                parts.append(f"기존 일정 장소: {', '.join(scheduled)}")

# sDB/dDB — 구현 완료 후 자동으로 추가됨
        if qust.sDB and isinstance(qust.sDB, dict):
            lines = []
            for day, cat_dict in qust.sDB.items():
                day_places = []
                for cat, items in cat_dict.items():
                    day_places.extend([f"{p.name}({p.main_category}, {p.region})" for p in items])
                if day_places:
                    lines.append(f"{day}일차: {', '.join(day_places)}")
            parts.append("방문 가능한 장소 (일차별):\n" + "\n".join(lines))

        if qust.dDB:
            lines = []
            for w in qust.dDB:
                line = f"{w.location} {w.forecast_time}시: {w.summary}"
                if w.rain_prob:
                    line += f", 강수확률 {w.rain_prob}%"
                line += f", 기온 {w.temperature}°C"
                lines.append(line)
            parts.append("날씨 조건:\n" + "\n".join(lines))

        # [신규 추가] sDB가 넘겨준 미매칭 키워드 검색 요청 덧붙이기
        if qust.PPL:
            parts.append(f"[추가 집중 검색 요청 - 반드시 이 조건에 맞는 장소를 최우선으로 찾아 포함할 것]:\n{qust.PPL}")
            
        return "\n\n".join(parts)

    @staticmethod
    def _parse_route_data(text: str) -> dict:
        """경로 번호별 {name, keywords} 추출. 키워드 줄이 없는 블록은 건너뜀."""
        route_data = {}
        blocks = re.split(r'\n(?=\d+\.)', text.strip())
        for block in blocks:
            name_m = _RE_ROUTE_NAME.match(block.strip())
            kw_m   = _RE_KEYWORDS.search(block)
            if not name_m or not kw_m:
                continue
            # 경로 번호 추출
            num_str = block.strip().split('.', 1)[0]
            try:
                num = int(num_str)
            except ValueError:
                continue
            keywords = [kw.strip() for kw in kw_m.group(1).split(',') if kw.strip()]
            route_data[num] = {"name": name_m.group(1).strip(), "keywords": keywords}
        return route_data

    @staticmethod
    def _clean(text: str) -> str:
        if not text:
            return text

        text = _RE_CITATION.sub("", text)
        text = _RE_BOLD.sub(r"\1", text)
        text = _RE_ITALIC.sub(r"\1", text)
        text = _RE_CODE.sub(r"\1", text)
        text = _RE_URL.sub("", text)
        text = _RE_META.sub("", text)
        text = _RE_BLANK.sub("\n\n", text)

        return text.strip()

    async def run(self, qust: "QUST") -> "QUST":
        if not self._api_key:
            return qust

        client = _get_client(self._api_key)
        prompt = self._build_prompt(qust)

        try:
            response = await client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception:
            qust.PPL = ""
            return qust

        if not response or not response.choices:
            qust.PPL = ""
            return qust

        content = response.choices[0].message.content or ""
        qust.route_keywords = self._parse_route_data(content)
        qust.PPL = self._clean(content)
        return qust
