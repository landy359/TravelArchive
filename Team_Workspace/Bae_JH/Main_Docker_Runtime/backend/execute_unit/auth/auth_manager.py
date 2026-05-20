# [역할] 세션 수립 이후의 인증 관리. 세 가지 책임을 가진다.
#
#        1. JWT 유틸 (모듈 레벨 함수) — Loader와 auth_kakao가 import해서 사용
#           create_access_token / create_refresh_token / verify_* — 토큰 발급·검증
#
#        2. FastAPI DI — facade.py가 모든 엔드포인트에 Depends로 주입
#           get_current_user  — 필수 인증
#           get_optional_user — 비로그인 허용
#
#        3. AuthManager 클래스
#           logout / refresh_token / get_my_info → EventHandler(priority) → Loader
#
#        호출 방향: AuthUnit → AuthManager → EventHandler(priority) → Loader
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

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

# ── JWT 설정 ──────────────────────────────────────────────────
ACCESS_TOKEN_SECRET_KEY      = os.getenv("ACCESS_TOKEN_SECRET_KEY", "")
REFRESH_TOKEN_SECRET_KEY     = os.getenv("REFRESH_TOKEN_SECRET_KEY", "")

if not ACCESS_TOKEN_SECRET_KEY or not REFRESH_TOKEN_SECRET_KEY:
    raise RuntimeError(
        "ACCESS_TOKEN_SECRET_KEY 또는 REFRESH_TOKEN_SECRET_KEY 환경변수가 설정되지 않았습니다. "
        "빈 JWT 시크릿으로 서버를 시작할 수 없습니다."
    )
ACCESS_TOKEN_EXPIRE_MINUTES  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS    = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
ALGORITHM = "HS256"


def create_access_token(user_id: str) -> str:
    now    = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  str(uuid.uuid4()),
        "exp":  expire,
    }
    return jwt.encode(payload, ACCESS_TOKEN_SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, ttl_seconds: int = None) -> tuple[str, str]:
    now = datetime.now(tz=timezone.utc)
    if ttl_seconds is None:
        ttl_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    expire = now + timedelta(seconds=ttl_seconds)
    jti    = str(uuid.uuid4())
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  jti,
        "exp":  expire,
    }
    return jwt.encode(payload, REFRESH_TOKEN_SECRET_KEY, algorithm=ALGORITHM), jti


def verify_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, ACCESS_TOKEN_SECRET_KEY, algorithms=[ALGORITHM])
        if "sub" not in payload:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰")


def verify_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, REFRESH_TOKEN_SECRET_KEY, algorithms=[ALGORITHM])
        if "sub" not in payload or "jti" not in payload:
            raise HTTPException(status_code=401, detail="유효하지 않은 갱신 토큰")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="갱신 토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 갱신 토큰")


# ── FastAPI DI ────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    payload = verify_access_token(token)
    return payload["sub"]


async def get_optional_user(token: str = Depends(oauth2_scheme)) -> str | None:
    if not token:
        return None
    try:
        payload = verify_access_token(token)
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
