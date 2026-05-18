"""
chat_session_container.py  [domain / chat 카테고리]

역할:
  LLM 대화 세션의 상태를 보관하는 컨테이너. ChatService가 메시지 처리마다 생성.
  - 세션 메타 (topic, name, context, is_manual_title) — Redis 로드·저장
  - 사용자 개인화 문자열 (personalized_topics)        — Redis에서 읽기
  - 메시지 버퍼 (past_messages, current_message)       — Redis 로드·저장
  - LLM 노드 3종: generation_node / topic_node / summary_node

설계 원칙 (Redis-first):
  매 요청마다 ChatService._get_container()가 새 인스턴스를 생성하고
  load_from_redis()로 상태 복원. Python 레벨 캐시 없음.
  상태 변경 → _save_meta() / _save_buffer()로 즉시 Redis 반영.
  PG 동기화는 blur/logout/idle_sweep 인터럽트가 담당 (chat_flush_service 참조).

임시 세션:
  load_from_redis()를 호출하지 않으면 _redis=None 유지 →
  _save_meta·_save_buffer가 no-op → in-memory 전용 동작.

Redis Keys:
  session:{id}:meta      → Hash   (topic, name, context, is_manual_title)
  session:{id}:buf_msgs  → JSON   (past_messages 버퍼)
  session:{id}:msg_count → String (total_user_msg_count)
  user:{id}:profile      → Hash   (personalized_topics 필드)
"""
import sys
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from setting.config import (
    LLM_MODEL_GENERATION, GENERATION_PROMPT, GENERATION_API_KEY,
    LLM_MODEL_TOPIC, TOPIC_PROMPT, TOPIC_API_KEY,
    LLM_MODEL_SUMMARY, SUMMARY_PROMPT, SUMMARY_API_KEY
)

from ...kernel.gpt_node import GptNode as TestNode

SESSION_META_TTL = 3600 * 8   # 8시간
BUF_TTL          = 3600 * 8


class SessionContainer:
    """
    Redis-backed 세션 컨테이너.
    컨테이너 객체는 매 요청마다 새로 생성되고, load_from_redis()로 상태를 복원한다.
    모든 상태 쓰기는 Redis에만. PG 동기화는 인터럽트(blur/logout/idle_sweep)가 담당.
    """

    def __init__(self, session_id: str, user_id: str,
                 max_buffer_size: int = 6, rename_threshold: int = 6):
        self.session_id = session_id
        self.user_id    = user_id
        self.max_buffer_size  = max_buffer_size
        self.rename_threshold = rename_threshold

        self.generation_node = TestNode(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY)
        self.topic_node      = TestNode(model_name=LLM_MODEL_TOPIC,      api_key=TOPIC_API_KEY)
        self.summary_node    = TestNode(model_name=LLM_MODEL_SUMMARY,    api_key=SUMMARY_API_KEY)

        # 상태 (load_from_redis 후 채워짐)
        self.personalization_topic: str = ""
        self.session_topic: str         = "새로운 대화"
        self.session_name: str          = "새 세션"
        self.session_context: str       = ""
        self.is_manual_title: bool      = False
        self.total_user_msg_count: int  = 0
        self.past_messages: List[Dict]  = []
        self.current_message: Optional[Dict] = None

        self.is_processing: bool = False
        self._redis = None   # load_from_redis() 호출 후 세팅

    # ──────────────────────────────────────────────────────────
    # Redis 로드 / 저장
    # ──────────────────────────────────────────────────────────

    async def load_from_redis(self, redis) -> None:
        """모든 상태를 Redis에서 복원. 컨테이너 생성 직후 반드시 호출."""
        from ...memory.cacher import Cacher
        self._redis = redis

        meta = await Cacher.get_session_meta(self.session_id, redis)
        if meta:
            self.session_topic    = meta.get("topic",           "새로운 대화")
            self.session_name     = meta.get("name",            "새 세션")
            self.session_context  = meta.get("context",         "")
            self.is_manual_title  = meta.get("is_manual_title", "false") == "true"

        self.personalization_topic = await Cacher.get_personalized_topics(self.user_id, redis)
        self.past_messages         = await Cacher.get_session_buf(self.session_id, redis)
        self.total_user_msg_count  = await Cacher.get_session_msg_count(self.session_id, redis)

    async def _save_meta(self) -> None:
        """세션 메타를 Redis에 쓰고 dirty 마킹. 임시 세션(_redis=None)은 스킵."""
        if not self._redis:
            return
        from ...memory.cacher import Cacher
        await Cacher.cache_session_meta(self.session_id, {
            "topic":           self.session_topic,
            "name":            self.session_name,
            "context":         self.session_context,
            "is_manual_title": "true" if self.is_manual_title else "false",
        }, self._redis)
        await Cacher.mark_dirty_widget(self.session_id, "meta", self._redis)

    async def _save_buffer(self) -> None:
        """메시지 버퍼와 카운트를 Redis에 저장. 임시 세션(_redis=None)은 스킵."""
        if not self._redis:
            return
        from ...memory.cacher import Cacher
        await Cacher.save_session_buf(self.session_id, self.past_messages, self._redis)
        await Cacher.save_session_msg_count(self.session_id, self.total_user_msg_count, self._redis)

    # ──────────────────────────────────────────────────────────
    # 게터
    # ──────────────────────────────────────────────────────────

    def get_session_id(self) -> str:
        return self.session_id

    def get_session_name(self) -> str:
        return self.session_name

    def get_is_processing(self) -> bool:
        return self.is_processing

    # ──────────────────────────────────────────────────────────
    # 메인 파이프라인
    # ──────────────────────────────────────────────────────────

    async def ingest_message(self, text: str) -> bool:
        """사용자 메시지를 버퍼에 등록하고 주제 추론."""
        if self.current_message:
            self.past_messages.append(self.current_message)

        self.current_message = {"role": "user", "content": text}

        topic_result = await self._llm_update_topic(self.current_message, self.past_messages)
        topic_changed = (
            self.session_topic != topic_result["topic"]
            or self.session_name != topic_result["name"]
        )
        self.session_topic = topic_result["topic"]
        self.session_name  = topic_result["name"]

        if topic_changed:
            await self._save_meta()
        await self._save_buffer()

        return topic_changed

    async def generate_bot_response(self, query: str) -> str:
        """LLM 응답 생성 후 버퍼 저장."""
        bot_text = await self._node_network_generate(
            self.personalization_topic,
            self.session_topic,
            self.session_context,
            self.past_messages,
            self.current_message or {"role": "user", "content": query},
        )

        if self.current_message:
            self.past_messages.append(self.current_message)
        self.current_message = {"role": "bot", "content": bot_text}

        await self._check_and_flush_buffer()
        return bot_text

    async def process_user_input(self, text: str) -> str:
        """임시 세션 전용: 주제추론 + LLM 응답을 한 번에."""
        self.is_processing = True
        try:
            await self.ingest_message(text)
            return await self.generate_bot_response(text)
        except Exception as e:
            print(f"[{self.session_id}] process_user_input 오류: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            self.is_processing = False

    # ──────────────────────────────────────────────────────────
    # 버퍼 관리
    # ──────────────────────────────────────────────────────────

    async def _check_and_flush_buffer(self) -> None:
        if len(self.past_messages) < self.max_buffer_size:
            await self._save_buffer()
            return

        print(f"[{self.session_id}] 버퍼 한계 도달. 요약 및 Flush.")

        new_context = await self._llm_summarize_context(
            self.session_context, self.past_messages
        )
        self.session_context = new_context
        self.past_messages.clear()

        await self._save_meta()
        await self._save_buffer()

    async def teardown(self) -> None:
        """세션 변경/종료 시 버퍼를 Redis에 최종 저장."""
        if self.current_message:
            self.past_messages.append(self.current_message)
            self.current_message = None

        await self._check_and_flush_buffer()
        await self._save_meta()

    # ──────────────────────────────────────────────────────────
    # LLM 연동
    # ──────────────────────────────────────────────────────────

    async def _llm_update_topic(self, current_msg: dict, past_msgs: List[dict]) -> dict:
        if current_msg.get("role") == "user":
            self.total_user_msg_count += 1

        suggested_name  = self.session_name
        suggested_topic = self.session_topic

        print(f"[{self.session_id}] 주제 갱신 LLM 가동. (총 {self.total_user_msg_count}번째 메시지)")

        history_text = ""
        for msg in past_msgs:
            role_kr = "사용자" if msg["role"] == "user" else "AI"
            history_text += f"{role_kr}: {msg['content']}\n"
        history_text += f"사용자: {current_msg['content']}"

        prompt = TOPIC_PROMPT.format(history_text=history_text)

        try:
            response = await self.topic_node.ask(prompt)
            response_clean = response.replace("```json", "").replace("```", "").strip()
            result = json.loads(response_clean)

            suggested_topic = result.get("topic", suggested_topic)
            if not self.is_manual_title:
                suggested_name = result.get("name", suggested_name)
        except Exception as e:
            print(f"[{self.session_id}] 주제 갱신 노드 에러 (기존 값 유지): {e}")

        return {"topic": suggested_topic, "name": suggested_name}

    async def _node_network_generate(self, p_topic: str, s_topic: str, s_context: str,
                                      past_msgs: List[dict], current_msg: dict) -> str:
        past_chat_history = ""
        if past_msgs:
            for msg in past_msgs:
                role_kr = "사용자" if msg["role"] == "user" else "AI"
                past_chat_history += f"{role_kr}: {msg['content']}\n"
        else:
            past_chat_history = "최근 대화 내역 없음"

        prompt = GENERATION_PROMPT.format(
            p_topic=p_topic,
            s_topic=s_topic,
            s_context=s_context,
            past_chat_history=past_chat_history,
            current_msg_content=current_msg["content"],
        )
        result = await self.generation_node.ask(prompt)
        if not result or result.startswith("ERROR:"):
            print(f"[{self.session_id}] LLM 응답 실패: {result}")
            return "AI 응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
        return result

    async def _llm_summarize_context(self, current_context: str, past_msgs: List[dict]) -> str:
        print(f"[{self.session_id}] 과거 버퍼 요약 LLM 가동.")

        history_text = ""
        for msg in past_msgs:
            role_kr = "사용자" if msg["role"] == "user" else "AI"
            history_text += f"{role_kr}: {msg['content']}\n"

        prompt = SUMMARY_PROMPT.format(
            current_context=current_context if current_context else "없음",
            history_text=history_text,
        )

        try:
            response = await self.summary_node.ask(prompt)
            return response.strip()
        except Exception as e:
            print(f"[{self.session_id}] 요약 노드 에러 (기존 값 유지): {e}")
