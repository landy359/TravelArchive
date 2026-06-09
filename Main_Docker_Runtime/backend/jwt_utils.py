"""
JWT 토큰 발급·검증 유틸리티.
auth_manager, auth_kakao, loader 세 곳에서 공통으로 사용.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

ACCESS_TOKEN_SECRET_KEY  = os.getenv("ACCESS_TOKEN_SECRET_KEY", "")
REFRESH_TOKEN_SECRET_KEY = os.getenv("REFRESH_TOKEN_SECRET_KEY", "")

if not ACCESS_TOKEN_SECRET_KEY or not REFRESH_TOKEN_SECRET_KEY:
    raise RuntimeError(
        "ACCESS_TOKEN_SECRET_KEY 또는 REFRESH_TOKEN_SECRET_KEY 환경변수가 설정되지 않았습니다. "
        "빈 JWT 시크릿으로 서버를 시작할 수 없습니다."
    )

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
ALGORITHM = "HS256"


def create_access_token(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  str(uuid.uuid4()),
        "iat":  int(now.timestamp()),
        "exp":  now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, ACCESS_TOKEN_SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, ttl_seconds: int = None) -> tuple[str, str]:
    now = datetime.now(tz=timezone.utc)
    if ttl_seconds is None:
        ttl_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    jti = str(uuid.uuid4())
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  jti,
        "exp":  now + timedelta(seconds=ttl_seconds),
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
