# [역할] KKO(카카오) 계정의 OAuth 로직 전담.
#        외부 카카오 API 호출과 JWT 발급만 담당한다.
#        DB 조회/생성은 EventHandler(manager) → Loader 경유로만 처리한다.
#
#        흐름:
#          로그인/가입: get_kakao_auth_url → (카카오 리다이렉트) → kakao_callback → JWT 발급
#          계정 연동:   initiate_kakao_link → (카카오 리다이렉트) → kakao_callback(state 있음) → DB 연동
#
#        호출 방향: AuthRequest → auth_kakao → EventHandler(manager) → Loader
import asyncio
import os
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp
from fastapi import HTTPException

from ...jwt_utils import create_access_token, create_refresh_token, REFRESH_TOKEN_EXPIRE_DAYS
from ...memory.events import KakaoAuthRequestEvent

KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "")

_TTL_REFRESH = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


def _check_kakao_config() -> None:
    if not KAKAO_CLIENT_ID or not KAKAO_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="카카오 로그인이 설정되지 않았습니다 (KAKAO_CLIENT_ID 또는 KAKAO_REDIRECT_URI 누락)")


def get_kakao_auth_url() -> str:
    """프론트엔드가 리다이렉트할 카카오 인가 URL 반환."""
    _check_kakao_config()
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


async def initiate_kakao_link(user_id: str, redis: Any) -> str:
    """
    계정 연동 흐름 시작.
    state 토큰을 Redis에 저장(5분 TTL)하고 카카오 인가 URL을 반환한다.
    """
    _check_kakao_config()
    link_token = str(uuid.uuid4())
    await redis.execute({
        "action": "set",
        "key": f"kakao_link:{link_token}",
        "value": user_id,
        "ttl": 300,
    })
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
        "state": link_token,
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


async def _exchange_code(code: str) -> str:
    """authorization code → 카카오 access_token 교환."""
    body = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
    }
    if KAKAO_CLIENT_SECRET:
        body["client_secret"] = KAKAO_CLIENT_SECRET

    async with aiohttp.ClientSession() as session:
        async with session.post("https://kauth.kakao.com/oauth/token", data=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(status_code=502, detail=f"카카오 토큰 교환 실패: {text[:200]}")
            data = await resp.json()
    return data["access_token"]


async def _get_user_info(kakao_access_token: str) -> dict[str, Any]:
    """카카오 access_token → 사용자 정보 조회."""
    headers = {"Authorization": f"Bearer {kakao_access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://kapi.kakao.com/v2/user/me", headers=headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="카카오 사용자 정보 조회 실패")
            return await resp.json()


async def kakao_callback(
    code: str,
    redis: Any,
    manager: Any,
    state: Optional[str] = None,
) -> dict[str, Any]:
    """
    카카오 콜백 처리.
    DB 조회/생성/연동은 KakaoAuthRequestEvent로 EventHandler에 위임한다.
    """
    kakao_token = await _exchange_code(code)
    info = await _get_user_info(kakao_token)

    provider_uid = str(info["id"])
    kakao_account = info.get("kakao_account", {})
    kakao_profile = kakao_account.get("profile", {})
    nickname = kakao_profile.get("nickname", "")
    profile_img_url = kakao_profile.get("profile_image_url", "")
    email = kakao_account.get("email")

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    event = KakaoAuthRequestEvent(
        provider_uid=provider_uid,
        nickname=nickname,
        email=email,
        profile_img_url=profile_img_url,
        redis=redis,
        state=state,
        future=future,
    )
    await manager.emit_and_wait(event, priority=True)
    lookup = await future

    if lookup.get("linked"):
        return lookup

    user_id = lookup["user_id"]
    # 단일 기기 정책: 기존 refresh 토큰 전부 폐기 + last_login_at 갱신
    from ...memory.loader import Loader
    from ...execute_unit.system.system_notify import NotifyService
    from datetime import datetime, timezone
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    # 기존 세션 있으면 강제 로그아웃 이벤트 먼저 푸시
    existing = await redis.execute({"action": "smembers", "key": f"user:{user_id}:refresh_jtis"})
    if existing.get("data"):
        NotifyService.push_force_logout(user_id)
    await Loader.logout_all_devices(redis, user_id)
    await redis.set_str(f"user:{user_id}:last_login_at", str(now_ts), _TTL_REFRESH)
    access_token = create_access_token(user_id)
    refresh_token, jti = create_refresh_token(user_id)

    await redis.execute({
        "action": "set",
        "key": f"auth:refresh:{jti}",
        "value": user_id,
        "ttl": _TTL_REFRESH,
    })
    await redis.execute({
        "action": "sadd",
        "key": f"user:{user_id}:refresh_jtis",
        "member": jti,
    })

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "type": "KKO",
        "is_new": lookup.get("is_new", False),
        "nickname": lookup.get("nickname", nickname),
        "email": lookup.get("email", email),
        "status": "success",
    }
