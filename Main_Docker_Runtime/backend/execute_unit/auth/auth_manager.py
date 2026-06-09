# [역할] 세션 수립 이후의 인증 관리. 두 가지 책임을 가진다.
#
#        1. FastAPI DI — facade.py가 모든 엔드포인트에 Depends로 주입
#           get_current_user  — 필수 인증
#           get_optional_user — 비로그인 허용
#
#        2. AuthManager 클래스
#           logout / refresh_token / get_my_info → EventHandler(priority) → Loader
#
#        JWT 유틸(create_*/verify_*)은 backend/jwt_utils.py에 있다.
#
#        호출 방향: AuthUnit → AuthManager → EventHandler(priority) → Loader
import asyncio
import os
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from ...jwt_utils import verify_access_token  # noqa: F401 (re-used by DI below)
from ...memory.cacher import Cacher
from ...memory.events import (
    AdminCheckEmailEvent,
    AdminListUsersEvent,
    GetMyInfoRequestEvent,
    LogoutAllDevicesEvent,
    LogoutRequestEvent,
    RefreshRequestEvent,
)

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# ── FastAPI DI ────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def _check_token_validity(payload: dict, redis) -> bool:
    """False를 반환하면 토큰 무효 (단일 기기 정책 또는 명시적 revoke)."""
    jti = payload.get("jti")
    if jti and await redis.get_str(f"auth:revoked:{jti}"):
        return False
    iat = payload.get("iat")
    if iat:
        user_id = payload.get("sub", "")
        last_login = await redis.get_str(f"user:{user_id}:last_login_at")
        if last_login and int(iat) < int(last_login):
            return False
    return True


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    payload = verify_access_token(token)
    redis = getattr(getattr(request.app, "state", None), "redis", None)
    if redis and not await _check_token_validity(payload, redis):
        raise HTTPException(status_code=401, detail="다른 기기에서 로그인되어 로그아웃되었습니다")
    return payload["sub"]


async def get_optional_user(request: Request, token: str = Depends(oauth2_scheme)) -> str | None:
    if not token:
        return None
    try:
        payload = verify_access_token(token)
        redis = getattr(getattr(request.app, "state", None), "redis", None)
        if redis and not await _check_token_validity(payload, redis):
            return None
        return payload["sub"]
    except HTTPException:
        return None


# ── AuthManager ───────────────────────────────────────────────
class AuthManager:

    @staticmethod
    async def logout(refresh_token: str, user_id: Optional[str], manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(
            LogoutRequestEvent(refresh_token=refresh_token, user_id=user_id, future=future),
            priority=True,
        )
        return await future

    @staticmethod
    async def refresh_token(refresh_token: str, manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(RefreshRequestEvent(refresh_token=refresh_token, future=future), priority=True)
        return await future

    @staticmethod
    async def logout_all_devices(user_id: str, manager: Any) -> None:
        future = asyncio.get_running_loop().create_future()
        manager.emit(LogoutAllDevicesEvent(user_id=user_id, future=future), priority=True)
        await future

    @staticmethod
    async def check_admin(user_id: str, manager: Any) -> str:
        """관리자 확인 후 user_id 반환. 아니면 403."""
        future = asyncio.get_running_loop().create_future()
        manager.emit(AdminCheckEmailEvent(user_id=user_id, future=future), priority=True)
        email = await future
        if _ADMIN_EMAIL and email == _ADMIN_EMAIL:
            return user_id
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")

    @staticmethod
    async def admin_list_users(manager: Any) -> list:
        future = asyncio.get_running_loop().create_future()
        manager.emit(AdminListUsersEvent(future=future), priority=True)
        return await future

    @staticmethod
    async def get_my_info(user_id: str, redis: Any, manager: Any) -> Any:
        profile = await Cacher.get_user_profile(user_id, redis)
        if profile:
            return {
                "status":    "success",
                "user_id":   user_id,
                "user_type": user_id.split(":")[0],
                "nickname":  profile.get("nickname", ""),
                "email":     profile.get("email1", profile.get("email", "")),
            }
        future = asyncio.get_running_loop().create_future()
        manager.emit(GetMyInfoRequestEvent(user_id=user_id, future=future), priority=True)
        return await future
