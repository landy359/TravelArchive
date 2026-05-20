"""
chat_session_container.py

역할: LLM 대화 세션 상태 보관. ChatService가 요청마다 생성 후 load_from_redis()로 복원.

Redis Keys:
  session:{id}:meta      → Hash  (topic, name, context, is_manual_title)
  session:{id}:buf_msgs  → JSON  (past_messages)
  session:{id}:msg_count → String (total_user_msg_count)
  session:{id}:widgets   → JSON  (widget_state)
  user:{id}:profile      → Hash  (personalized_topics)

임시 세션: load_from_redis() 미호출 시 _redis=None → _save_* no-op → in-memory 전용.
"""
import json
from typing import List, Dict, Optional

from setting.config import (
    LLM_MODEL_GENERATION, GENERATION_PROMPT, GENERATION_API_KEY,
    LLM_MODEL_ABSORB, ABSORB_PROMPT, ABSORB_API_KEY,
)
from ...kernel.llm import LLM


class SessionContainer:

    def __init__(self, session_id: str, user_id: str, max_buffer_size: int = 6):
        self.session_id  = session_id
        self.user_id     = user_id
        self.max_buffer_size = max_buffer_size

        self._gen_node    = LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY)
        self._absorb_node = LLM(model_name=LLM_MODEL_ABSORB,     api_key=ABSORB_API_KEY)

        self.personalization_topic: str  = ""
        self.session_topic: str          = "새로운 대화"
        self.session_name: str           = "새 세션"
        self.session_context: str        = ""
        self.is_manual_title: bool       = False
        self.total_user_msg_count: int   = 0
        self.past_messages: List[Dict]   = []
        self.widget_state: Dict          = {"t_sl": "", "t_cd": [], "t_mp": [], "t_mk": [], "t_pn": []}
        self.last_topic_change: Optional[dict] = None
        self._redis = None

    # ── Redis ──────────────────────────────────────────────────

    async def load_from_redis(self, redis) -> None:
        from ...memory.cacher import Cacher
        self._redis = redis
        meta = await Cacher.get_session_meta(self.session_id, redis)
        if meta:
            self.session_topic   = meta.get("topic",           "새로운 대화")
            self.session_name    = meta.get("name",            "새 세션")
            self.session_context = meta.get("context",         "")
            self.is_manual_title = meta.get("is_manual_title", "false") == "true"
        self.personalization_topic = await Cacher.get_personalized_topics(self.user_id, redis)
        self.past_messages         = await Cacher.get_session_buf(self.session_id, redis)
        self.total_user_msg_count  = await Cacher.get_session_msg_count(self.session_id, redis)
        self.widget_state          = await Cacher.get_session_widgets(self.session_id, redis) or self.widget_state

    async def _save_meta(self) -> None:
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
        if not self._redis:
            return
        from ...memory.cacher import Cacher
        await Cacher.save_session_buf(self.session_id, self.past_messages, self._redis)
        await Cacher.save_session_msg_count(self.session_id, self.total_user_msg_count, self._redis)

    async def _save_widgets(self) -> None:
        if not self._redis:
            return
        from ...memory.cacher import Cacher
        await Cacher.save_session_widgets(self.session_id, self.widget_state, self._redis)

    # ── 외부 인터페이스 ─────────────────────────────────────────

    def router_context(self) -> dict:
        """Core.run()에 필요한 컨텍스트."""
        return {
            "history":       self.past_messages,
            "session_topic": self.session_topic,
            "usr_anal":      self.personalization_topic,
            "widget_state":  self.widget_state,
        }

    async def commit_turn(
        self,
        user_text: Optional[str] = None,
        bot_text:  Optional[str] = None,
        widget_state: Optional[dict] = None,
    ) -> None:
        """메시지(유저/봇) 커밋 → 저장 → absorb 판단."""
        if user_text:
            self.past_messages.append({"role": "user", "content": user_text})
            self.total_user_msg_count += 1
        if bot_text is not None:
            self.past_messages.append({"role": "bot", "content": bot_text})
        if widget_state is not None:
            self.widget_state = widget_state
        await self._save_buffer()
        await self._save_widgets()
        await self._absorb_if_needed()

    async def process_user_input(self, text: str) -> str:
        """임시 세션 전용: LLM 응답 생성 후 커밋."""
        bot_text = await self._generate(text)
        await self.commit_turn(user_text=text, bot_text=bot_text)
        return bot_text

    async def teardown(self) -> None:
        """세션 종료 시 미커밋 상태 정리."""
        await self.commit_turn()
        await self._save_meta()

    # ── 버퍼 / Absorb ──────────────────────────────────────────

    async def _absorb_if_needed(self) -> None:
        is_first = self.total_user_msg_count == 1
        buf_full = len(self.past_messages) >= self.max_buffer_size
        if not is_first and not buf_full:
            return

        absorbed = await self._llm_absorb()
        self.session_context = absorbed["context"]
        if not self.is_manual_title:
            new_name = absorbed["name"]
            if new_name != self.session_name:
                self.last_topic_change = {"prev": self.session_name, "new": new_name}
            self.session_name  = new_name
            self.session_topic = new_name

        if buf_full:
            self.past_messages.clear()
        await self._save_meta()
        await self._save_buffer()

    # ── LLM ────────────────────────────────────────────────────

    @staticmethod
    def _format_history(msgs: List[dict]) -> str:
        if not msgs:
            return "최근 대화 내역 없음"
        return "".join(
            f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}\n"
            for m in msgs
        )

    async def _generate(self, text: str) -> str:
        """임시 세션 전용 LLM 응답 생성."""
        prompt = GENERATION_PROMPT.format(
            p_topic=self.personalization_topic,
            s_topic=self.session_topic,
            s_context=self.session_context,
            past_chat_history=self._format_history(self.past_messages),
            current_msg_content=text,
        )
        result = await self._gen_node.ask(prompt)
        if not result or result.startswith("ERROR:"):
            result = "AI 응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
        return result

    async def _llm_absorb(self) -> dict:
        prompt = ABSORB_PROMPT.format(
            current_title=self.session_name,
            current_context=self.session_context or "없음",
            history_text=self._format_history(self.past_messages),
        )
        try:
            name, context = self.session_name, self.session_context
            for line in (await self._absorb_node.ask(prompt)).strip().splitlines():
                if line.startswith("title:"):
                    name = line[len("title:"):].strip()
                elif line.startswith("context:"):
                    context = line[len("context:"):].strip()
            return {"name": name, "context": context}
        except Exception as e:
            print(f"[{self.session_id}] absorb 실패 (기존 값 유지): {e}")
            return {"name": self.session_name, "context": self.session_context}
