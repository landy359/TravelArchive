"""
user_analyze.py  [domain / user 카테고리]

역할:
  사용자 성향을 델타 기반으로 점진적으로 갱신하는 분석기.
  트리거: (1) 세션 주제 변경(absorb), (2) 설정 저장
  출력: 한 문단 성향 요약 → Redis user:{id}:analysis + profile.personalized_topics

  cold start 없음: 의미 있는 데이터가 없으면 실행하지 않는다.
  데이터가 쌓일수록 요약이 정교해지는 구조.

  호출 방향: EventHandler(background task) → UserAnalyze → Cacher(Redis) + LLM(LLM)
"""
import asyncio
from typing import Any, Optional

from setting.config import LLM_MODEL_PERSONAL, PERSONAL_API_KEY, PERSONAL_PROMPT
from ...kernel.llm import LLM
from ...memory.cacher import Cacher
from ...memory.events import LoadUserSessionTopicsEvent

_DEFAULT_TOPICS = {"새로운 대화", "새 세션", ""}


def _strip_empty(d: dict) -> dict:
    """빈 문자열·빈 리스트를 제거해 LLM 프롬프트에 실질적 내용만 포함시킨다."""
    return {k: v for k, v in d.items() if v not in ("", [], None)}


def _future() -> asyncio.Future:
    return asyncio.get_running_loop().create_future()


class UserAnalyze:

    @staticmethod
    async def run_on_topic_change(
        user_id: str, session_id: str,
        prev_topic: str, new_topic: str,
        redis: Any, manager: Any,
    ) -> None:
        """absorb로 세션 주제가 바뀌었을 때 호출."""
        if not new_topic or new_topic in _DEFAULT_TOPICS:
            return

        prev_analysis = await Cacher.get_user_analysis(user_id, redis)

        if prev_topic and prev_topic not in _DEFAULT_TOPICS:
            delta_description = f"{prev_topic} → {new_topic}"
        else:
            delta_description = f"새 주제: {new_topic}"

        await UserAnalyze._run(
            user_id=user_id,
            session_id=session_id,
            prev_analysis=prev_analysis,
            delta_type="세션 주제 변경",
            delta_description=delta_description,
            redis=redis,
            manager=manager,
            style=None,
        )

    @staticmethod
    async def run_on_settings_change(
        user_id: str,
        style: dict, travel: dict,
        redis: Any, manager: Any,
    ) -> None:
        """설정 저장 시 호출 — AI 스타일·여행 스타일 변경분을 분석에 반영."""
        if not travel and not style:
            return

        await Cacher.save_user_analysis(user_id, "", redis)

        parts = []
        if style:
            parts.append(f"AI스타일: {style}")
        if travel:
            parts.append(f"여행취향: {travel}")

        await UserAnalyze._run(
            user_id=user_id,
            session_id=None,
            prev_analysis="",
            delta_type="설정 변경",
            delta_description=", ".join(parts),
            redis=redis,
            manager=manager,
            style=style,
        )

    @staticmethod
    async def _load_other_session_topics(
        user_id: str,
        session_id: Optional[str],
        manager: Any,
    ) -> list[str]:
        if not session_id:
            return []
        fut: asyncio.Future[list[str]] = _future()
        manager.emit(
            LoadUserSessionTopicsEvent(
                user_id=user_id,
                exclude_session_id=session_id,
                future=fut,
            ),
            priority=True,
        )
        return await asyncio.wait_for(asyncio.shield(fut), timeout=10.0)

    @staticmethod
    async def _run(
        user_id: str,
        session_id: Optional[str],
        prev_analysis: str,
        delta_type: str,
        delta_description: str,
        redis: Any,
        manager: Any,
        style: Optional[dict] = None,
    ) -> None:
        other_topics, travel, cached_style = await asyncio.gather(
            UserAnalyze._load_other_session_topics(user_id, session_id, manager),
            Cacher.get_user_travel(user_id, redis),
            Cacher.get_user_style(user_id, redis),
        )
        session_topics = ", ".join(other_topics) if other_topics else "없음"
        raw_style = style if style is not None else cached_style
        style_data = _strip_empty(raw_style) if raw_style else {}

        prompt = PERSONAL_PROMPT.format(
            prev_summary=prev_analysis if prev_analysis else "없음",
            delta_type=delta_type,
            delta_description=delta_description,
            session_topics=session_topics,
            style_settings=style_data if style_data else "없음",
            travel_settings=travel if travel else "없음",
        )

        node = LLM(model_name=LLM_MODEL_PERSONAL, api_key=PERSONAL_API_KEY)
        result = await node.ask(prompt)

        if not result or result.startswith("ERROR:"):
            print(f"[UserAnalyze] LLM 오류 ({user_id}): {result}")
            return

        analysis_text = result.strip()
        await Cacher.save_user_analysis(user_id, analysis_text, redis)
        from ..system.system_notify import NotifyService
        NotifyService.push_to_user(user_id, {"type": "analysis_update", "analysis": analysis_text})
        print(f"[UserAnalyze] {user_id} 성향 분석 갱신 완료")
