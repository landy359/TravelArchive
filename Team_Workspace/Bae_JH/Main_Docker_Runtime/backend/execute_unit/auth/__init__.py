# [역할] 인증 실행 단위. 순수 pass-through — 로직 없음.
#        최초 인증 요청은 AuthRequest로, 로그인 이후 관리는 AuthManager로 위임.
#
#        호출 방향: Facade → AuthUnit → AuthRequest / AuthManager (domain)
from typing import Any, Optional

from .auth_request import AuthRequest
from .auth_manager import AuthManager, get_current_user, get_optional_user


class AuthUnit:

    # ── 최초 인증 (auth_request) ─────────────────────────────

    @staticmethod
    async def signup(data: dict, manager: Any) -> Any:
        return await AuthRequest.signup(data, manager)

    @staticmethod
    async def login(email: str, password: str, manager: Any) -> Any:
        return await AuthRequest.login(email, password, manager)

    @staticmethod
    def get_kakao_auth_url() -> str:
        return AuthRequest.get_kakao_auth_url()

    @staticmethod
    async def kakao_callback(code: str, redis: Any, manager: Any, state: Optional[str] = None) -> dict:
        return await AuthRequest.kakao_callback(code, redis, manager, state)

    @staticmethod
    async def initiate_kakao_link(user_id: str, redis: Any) -> str:
        return await AuthRequest.initiate_kakao_link(user_id, redis)

    # ── 로그인 이후 관리 (auth_manager) ──────────────────────

    @staticmethod
    async def logout(refresh_token: str, user_id: Optional[str], manager: Any) -> Any:
        return await AuthManager.logout(refresh_token, user_id, manager)

    @staticmethod
    async def refresh_token(refresh_token: str, manager: Any) -> Any:
        return await AuthManager.refresh_token(refresh_token, manager)

    @staticmethod
    async def get_my_info(user_id: str, redis: Any, manager: Any) -> Any:
        return await AuthManager.get_my_info(user_id, redis, manager)
