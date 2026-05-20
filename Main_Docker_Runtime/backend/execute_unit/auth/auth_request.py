# [역할] 세션 수립 이전의 최초 인증 진입점.
#        MEM(이메일) 로그인/가입은 EventHandler priority queue로 직렬화하고,
#        KKO(카카오) OAuth는 외부 API 호출 후 EventHandler에 DB 작업을 위임한다.
#
#        호출 방향:
#          AuthUnit → AuthRequest → EventHandler(priority) → Loader  [MEM]
#          AuthUnit → AuthRequest → auth_kakao → EventHandler       [KKO]
import asyncio
from typing import Any, Optional

from ...memory.events import LoginRequestEvent, SignupRequestEvent
from .auth_kakao import get_kakao_auth_url, initiate_kakao_link, kakao_callback


class AuthRequest:

    @staticmethod
    async def signup(data: dict[str, Any], manager: Any) -> Any:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        manager.emit(SignupRequestEvent(data=data, future=future), priority=True)
        return await future

    @staticmethod
    async def login(email: str, password: str, manager: Any) -> Any:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        manager.emit(LoginRequestEvent(email=email, password=password, future=future), priority=True)
        return await future

    @staticmethod
    def get_kakao_auth_url() -> str:
        return get_kakao_auth_url()

    @staticmethod
    async def kakao_callback(code: str, redis: Any, manager: Any, state: Optional[str] = None) -> dict[str, Any]:
        result = await kakao_callback(code, redis, manager, state)
        # KKO: load_user_to_redis가 event_handler에서 이미 처리하므로 SignupEvent 불필요
        return result

    @staticmethod
    async def initiate_kakao_link(user_id: str, redis: Any) -> str:
        return await initiate_kakao_link(user_id, redis)
