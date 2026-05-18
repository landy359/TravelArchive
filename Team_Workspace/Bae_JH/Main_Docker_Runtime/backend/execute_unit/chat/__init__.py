# [역할] 채팅 내용 자체를 처리하는 실행 단위.
#        메시지 송수신·대화 기록 조회만 담당.
#        세션 CRUD·초대·파일·SSE·설정은 SystemUnit이 담당.
#
#        호출 방향: Facade → ChatUnit → ChatService → Cacher → manager(EventHandler)
from typing import Any

from .chat_service import ChatService


class ChatUnit:

    @staticmethod
    async def send_message(session_id: str, message: str, user_id: str,
                            redis: Any, manager: Any) -> Any:
        return await ChatService.send_message(session_id, message, user_id, redis, manager)

    @staticmethod
    async def get_chat_history(session_id: str, redis: Any, manager: Any,
                               limit: int = 40, offset: int = 0) -> dict:
        return await ChatService.get_chat_history(session_id, redis, manager,
                                                   limit=limit, offset=offset)

    @staticmethod
    async def send_temp_message(temp_session_id: str, message: str) -> Any:
        """비로그인 임시채팅. DB/Redis 저장 없음."""
        return await ChatService.send_temp_message(temp_session_id, message)
