"""
카카오 OAuth 로그인 서비스.
provider: kakao 전용 (naver/google 미지원).

흐름:
  1. GET /api/auth/kakao → get_kakao_auth_url() → 카카오 인가 페이지로 리다이렉트
  2. 카카오 → GET /api/auth/kakao/callback?code=...
  3. kakao_callback() → code 교환 → 사용자 정보 조회 → DB 신규/기존 처리 → JWT 발급
"""
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp
from fastapi import HTTPException

from module.node.memory.postgres_manager import PostgresManager
from module.node.memory.redis_manager import RedisManager
from .jwt_utils import create_access_token, create_refresh_token

KAKAO_CLIENT_ID     = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")  # 보안 강화 시 사용 (선택)
KAKAO_REDIRECT_URI  = os.getenv("KAKAO_REDIRECT_URI", "")

TTL_MEMBER = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")) * 24 * 3600


def get_kakao_auth_url() -> str:
    """프론트엔드가 리다이렉트할 카카오 인가 URL 반환."""
    if not KAKAO_CLIENT_ID:
        raise HTTPException(status_code=503, detail="카카오 로그인이 설정되지 않았습니다 (KAKAO_CLIENT_ID 누락)")
    params = {
        "client_id":     KAKAO_CLIENT_ID,
        "redirect_uri":  KAKAO_REDIRECT_URI,
        "response_type": "code",
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


async def initiate_kakao_link(user_id: str, redis: RedisManager) -> str:
    """
    계정 연동 흐름 시작.
    state 토큰을 Redis에 저장(5분 TTL)하고 카카오 인가 URL을 반환.
    콜백에서 state를 확인해 연동 vs 신규로그인을 분기한다.
    """
    if not KAKAO_CLIENT_ID:
        raise HTTPException(status_code=503, detail="카카오 로그인이 설정되지 않았습니다")
    link_token = str(uuid.uuid4())
    await redis.execute({
        "action": "set",
        "key":    f"kakao_link:{link_token}",
        "value":  user_id,
        "ttl":    300,  # 5분
    })
    params = {
        "client_id":     KAKAO_CLIENT_ID,
        "redirect_uri":  KAKAO_REDIRECT_URI,
        "response_type": "code",
        "state":         link_token,
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


async def _exchange_code(code: str) -> str:
    """authorization code → 카카오 access_token 교환."""
    body = {
        "grant_type":   "authorization_code",
        "client_id":    KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code":         code,
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


async def _get_user_info(kakao_access_token: str) -> dict:
    """카카오 access_token → 사용자 정보 조회."""
    headers = {"Authorization": f"Bearer {kakao_access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://kapi.kakao.com/v2/user/me", headers=headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="카카오 사용자 정보 조회 실패")
            return await resp.json()


async def kakao_callback(
    code: str,
    postgres: PostgresManager,
    redis: RedisManager,
    state: str = None,
) -> dict:
    """
    카카오 콜백 처리.
    - state가 Redis의 kakao_link:{state} 키와 매칭되면 → 계정 연동 (UserOAuth 레코드 추가)
    - 그 외 → 신규 KKO 계정 생성 또는 기존 KKO 계정 로그인 후 JWT 발급
    """
    kakao_token  = await _exchange_code(code)
    info         = await _get_user_info(kakao_token)

    provider_uid    = str(info["id"])
    kakao_account   = info.get("kakao_account", {})
    kakao_profile   = kakao_account.get("profile", {})
    nickname        = kakao_profile.get("nickname", "")
    profile_img_url = kakao_profile.get("profile_image_url", "")
    email           = kakao_account.get("email")

    now = datetime.now(tz=timezone.utc)

    # ── 계정 연동 흐름 ──────────────────────────────────────
    if state:
        link_key = f"kakao_link:{state}"
        link_result = await redis.execute({"action": "get", "key": link_key})
        link_user_id = link_result.get("value") if link_result else None

        if link_user_id:
            # Redis 키 소비 (1회용)
            await redis.execute({"action": "delete", "key": link_key})

            # 이미 연동된 카카오 계정인지 확인
            existing = await postgres.execute({
                "action":  "read",
                "model":   "UserOAuth",
                "filters": {"provider": "kakao", "provider_uid": provider_uid},
            })
            if existing.get("status") == "success" and existing.get("data"):
                raise HTTPException(status_code=409, detail="이미 다른 계정에 연동된 카카오 계정입니다")

            oauth_id = "oauth_" + str(uuid.uuid4())[:16]
            result = await postgres.execute({
                "action": "create", "model": "UserOAuth",
                "data": {
                    "oauth_id":    oauth_id,
                    "user_id":     link_user_id,
                    "provider":    "kakao",
                    "provider_uid": provider_uid,
                    "created_at":  now,
                },
            })
            if result.get("status") != "success":
                raise HTTPException(status_code=500, detail="카카오 계정 연동 실패")

            return {"linked": True, "user_id": link_user_id}

    # ── 일반 로그인/신규 가입 흐름 ─────────────────────────
    oauth_result = await postgres.execute({
        "action":  "read",
        "model":   "UserOAuth",
        "filters": {"provider": "kakao", "provider_uid": provider_uid},
    })

    if oauth_result.get("status") == "success" and oauth_result.get("data"):
        user_id = oauth_result["data"][0]["user_id"]
    else:
        user_id  = "KKO:" + str(uuid.uuid4())[:16]
        oauth_id = "oauth_" + str(uuid.uuid4())[:16]

        for payload in [
            {"action": "create", "model": "User",
             "data": {"user_id": user_id, "user_type": "KKO", "status": "active", "created_at": now}},
            {"action": "create", "model": "UserOAuth",
             "data": {"oauth_id": oauth_id, "user_id": user_id,
                      "provider": "kakao", "provider_uid": provider_uid, "created_at": now}},
            {"action": "create", "model": "UserProfile",
             "data": {"user_id": user_id, "email": email, "nickname": nickname,
                      "profile_img_url": profile_img_url, "updated_at": now}},
            {"action": "create", "model": "UserPreferences",
             "data": {"user_id": user_id, "updated_at": now}},
        ]:
            result = await postgres.execute(payload)
            if result.get("status") != "success":
                raise HTTPException(
                    status_code=500,
                    detail=f"KKO 계정 생성 실패 ({payload['model']}): {result.get('reason')}",
                )

    access_token       = create_access_token(user_id)
    refresh_token, jti = create_refresh_token(user_id)

    await redis.execute({
        "action": "set", "key": f"auth:refresh:{jti}", "value": user_id, "ttl": TTL_MEMBER,
    })

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user_id":       user_id,
        "type":          "KKO",
        "nickname":      nickname,
        "email":         email,
        "status":        "success",
    }
