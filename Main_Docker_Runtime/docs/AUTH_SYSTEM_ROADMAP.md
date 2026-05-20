# 인증 시스템 구축 로드맵 — 이중키 Redis-JWT 방식

> 작성 기준일: 2026-04-10 (갱신)
> 대상 독자: 이 프로젝트를 처음 보는 개발자 또는 AI
> 목적: 로그인·인증·계정 시스템 전체를 처음부터 구축하기 위한 단계별 명세

---

## 0. 이중키(Dual-Key) JWT 방식이란?

일반 JWT는 Access Token 하나만 사용해 만료 후 재로그인을 강요하거나,
긴 만료 시간을 줘서 탈취 위험을 높인다.

이중키 방식은 두 종류의 토큰을 **각기 다른 서명 키**로 발급하여 아래 위험을 차단한다:

```
[단일키 방식의 문제]
  Access Token 서명키 = Refresh Token 서명키
  → 서버 측에서 두 토큰을 구분하는 로직이 없으면
    Refresh Token을 Authorization 헤더에 끼워 API를 호출해도 통과될 수 있음
  → 키 하나가 유출되면 두 토큰이 모두 위조 가능

[이중키 방식의 해결]
  ACCESS_TOKEN_SECRET_KEY  (짧은 만료 15~60분)
  REFRESH_TOKEN_SECRET_KEY (긴 만료 7일, Redis에 저장 필수)
  → verify_access_token()은 ACCESS 키로만 검증 → Refresh Token은 파싱 실패
  → verify_refresh_token()은 REFRESH 키로만 검증 → Access Token은 파싱 실패
  → 키 유출 시 피해 범위가 절반으로 줄어듦
```

**Redis가 추가로 하는 역할:**
- Refresh Token의 `jti`(고유 ID)를 Redis에 저장 → 로그아웃 시 삭제
- Redis에 없는 `jti`로 refresh 시도 → 즉시 401 반환 (JWT 서명이 유효해도 거부)
- 이것이 **"서버 측 토큰 무효화"** — JWT의 본질적 약점(발급 후 취소 불가)을 Redis로 보완

---

## 1. 프로젝트 현재 상태

### 1-1. 기술 스택

| 레이어 | 기술 |
|--------|------|
| 웹 프레임워크 | FastAPI (Python 3.10) |
| 관계형 DB | PostgreSQL 18 + PostGIS (Docker: `TA_db`) |
| 인메모리 DB | Redis 7 (Docker: `TA_redis`) |
| ORM | SQLAlchemy (동기, `asyncio.to_thread`로 비동기 래핑) |
| 마이그레이션 | Alembic |
| 인증 라이브러리 | PyJWT, passlib[bcrypt] (설치됨, 미구현) |
| 리버스 프록시 | Nginx |
| 컨테이너 | Docker Compose (컴포즈 파일 분리 운영) |

### 1-2. 현재 디렉토리 구조 (핵심 파일만)

```
Main_Docker_Runtime/
├── backend/
│   └── facade.py              ← FastAPI 진입점. 현재 Mock DB 사용 중
├── module/
│   └── node/
│       └── memory/
│           ├── postgres_manager.py   ← PostgreSQL CRUD (완성)
│           ├── postgres_node.py      ← 파이프라인용 노드 (완성)
│           ├── postgres_tables.py    ← SQLAlchemy ORM 모델 (완성)
│           ├── redis_manager.py      ← Redis CRUD (완성)
│           ├── redis_node.py         ← 파이프라인용 노드 (완성)
│           └── redis_tables.py       ← Redis DTO 클래스 (완성)
├── alembic/
│   ├── env.py                 ← DATABASE_URL 주입, Base 감지 설정 (완성)
│   ├── script.py.mako
│   └── versions/              ← 비어 있음. 마이그레이션 파일이 쌓일 곳
├── alembic.ini
├── setting/
│   ├── .env                   ← 실제 환경 변수 (git 제외)
│   ├── .env.sample            ← 환경 변수 템플릿
│   └── config.py              ← LLM 설정 로드
├── db/
│   └── init.sql               ← PostGIS 확장 활성화만 담당
└── requirements.txt           ← PyJWT, passlib[bcrypt], alembic 포함됨
```

### 1-3. 현재 문제점 (구축 전 상태)

- `facade.py`의 모든 auth 엔드포인트가 Mock 응답만 반환함
- `user_id = "default_user"` 하드코딩 — 모든 세션이 같은 사용자 것으로 처리됨
- 세션 데이터가 Python 인메모리 dict에만 저장됨 (서버 재시작 시 소멸)
- PostgreSQL 테이블이 실제로 존재하지 않음 (Alembic 미실행)
- `api.js`가 Authorization 헤더를 전송하지 않음 (프론트엔드 토큰 연동 없음)

---

## 2. 사용자 식별 체계

> 이 프로젝트 전체에서 사용자를 구별하는 핵심 규칙. 모든 코드가 이 형식을 따라야 함.

### 2-1. user_id 포맷

```
{타입코드}:{고유값}

MEM:{uuid4}        ← 일반 회원 (Member)
GST:{uuid4}        ← 게스트 (Guest)
KKO:{sha256[:16]}  ← 카카오 SNS
NVR:{sha256[:16]}  ← 네이버 SNS
GGL:{sha256[:16]}  ← 구글 SNS
```

**규칙:**
- 타입코드는 항상 3자리 대문자
- `user_id.split(":")[0]` 으로 타입을 즉시 판별할 수 있어야 함
- GST는 PostgreSQL에 저장하지 않음. Redis에만 존재

### 2-2. JWT 이중키 구조

**Access Token** (만료: 15~60분, `.env`의 `ACCESS_TOKEN_EXPIRE_MINUTES`)
```json
{
  "sub": "MEM:a3f2b1c4-...",
  "type": "MEM",
  "jti": "랜덤 UUID",
  "exp": 1712345678
}
서명 키: ACCESS_TOKEN_SECRET_KEY
```

**Refresh Token** (만료: 7일, `.env`의 `REFRESH_TOKEN_EXPIRE_DAYS`)
```json
{
  "sub": "MEM:a3f2b1c4-...",
  "type": "MEM",
  "jti": "랜덤 UUID (Access와 다른 별도 UUID)",
  "exp": 1712999999
}
서명 키: REFRESH_TOKEN_SECRET_KEY  ← Access Token 키와 반드시 다른 값
```

**왜 jti가 두 토큰에 각각 다른 UUID여야 하는가:**
- Access Token의 `jti`는 사용 안 함 (짧은 만료라 Redis 저장 불필요)
- Refresh Token의 `jti`가 Redis의 키로 사용됨: `auth:refresh:{jti}`
- 두 jti가 같으면 Access Token이 Redis를 오염시킬 위험이 있음

### 2-3. Redis 키 전체 구조

```
auth:refresh:{jti}          → String: user_id         (TTL: 7일)
user:GST:{uuid}             → Hash:   GuestUser 필드  (TTL: 24시간)
session:{id}:meta           → Hash:   SessionMeta 필드(TTL: MEM=48h, GST=24h)
session:{id}:state          → String: idle/processing  (TTL: 세션 수명)
user:{user_id}:sessions     → Set:    session_id 목록  (TTL: MEM=48h, GST=24h)
queue:tasks                 → List:   Task JSON 문자열 (TTL 없음)
```

> 이미 `redis_tables.py`에 DTO 클래스로 구현 완료. 새로 만들 필요 없음.

### 2-4. TTL 정책

| 대상 | TTL |
|------|-----|
| Refresh Token (`auth:refresh:{jti}`) | 7일 |
| 회원(MEM/SNS) 세션 데이터 | 48시간 |
| 게스트(GST) 전체 데이터 | 24시간 |
| 게스트 Refresh Token | 24시간 (GuestUser와 동일) |

### 2-5. 게스트 생명주기

```
접속
  └→ GST:uuid 생성
       └→ Redis에만 저장 (TTL 24h)
            ├→ 24시간 내 재접속 없음 → TTL 만료 → 자동 소멸
            └→ 회원가입/로그인 → PostgreSQL로 마이그레이션
```

---

## 3. 전체 데이터 흐름 (상세 전개도)

### 3-1. 회원가입 흐름

```
[프론트엔드: account.js]
    │ POST /api/auth/signup
    │ Body: { username, email, password }
    ▼
[facade.py: POST /api/auth/signup]
    │ auth_service.signup(postgres, data)
    ▼
[auth_service.signup()]
    ├─ (1) PostgresManager로 user_profile에서 email 중복 조회
    │       중복 시 HTTPException(409, "이미 가입된 이메일")
    │
    ├─ (2) user_id = "MEM:" + str(uuid4())  생성
    │
    ├─ (3) PostgresManager.insert():
    │       users 테이블:         { user_id, user_type="MEM", status="active" }
    │       user_profile 테이블:  { user_id, email, name=username, nickname=username }
    │       user_security 테이블: { user_id, password_hash=hash_password(password) }
    │       user_preference 테이블: { user_id } (빈 row, UI 설정 기본값)
    │
    └─ (4) 반환: { user_id }
    │
    ▼
[facade.py 응답]
    { "status": "success", "user_id": "MEM:xxxx" }

[프론트엔드]
    → 자동으로 /api/auth/login 호출하여 토큰 수령
```

**PostgreSQL 테이블 변경:**
- `users`, `user_profile`, `user_security`, `user_preference` — 이미 `postgres_tables.py`에 정의됨
- Alembic 마이그레이션 실행만 하면 됨

---

### 3-2. 일반 로그인 흐름

```
[프론트엔드: api.js → login(id, pw)]
    │ POST /api/auth/login
    │ Body: { id: "user@email.com", pw: "plaintext" }
    ▼
[facade.py: POST /api/auth/login]
    │ auth_service.login(postgres, redis, id, pw)
    ▼
[auth_service.login()]
    ├─ (1) PostgresManager로 user_profile에서 email=id 조회
    │       없으면 HTTPException(401, "존재하지 않는 계정")
    │
    ├─ (2) PostgresManager로 user_security에서 user_id로 password_hash 조회
    │
    ├─ (3) password_utils.verify_password(pw, password_hash)
    │       실패 시:
    │         user_security.login_fail_count += 1
    │         5회 이상이면 locked_until = now + 30분 설정
    │         HTTPException(401, "비밀번호 불일치")
    │       잠금 상태 확인:
    │         locked_until > now 이면 HTTPException(403, "계정 잠김")
    │
    ├─ (4) user_security.last_login_at = now, login_fail_count = 0 갱신
    │
    ├─ (5) jwt_utils.create_access_token(user_id)
    │       → payload: { sub, type, jti=uuid4(), exp=now+ACCESS_EXPIRE }
    │       → 서명: ACCESS_TOKEN_SECRET_KEY (HS256)
    │       → access_token 문자열 반환
    │
    ├─ (6) jwt_utils.create_refresh_token(user_id)
    │       → payload: { sub, type, jti=uuid4() [Access의 jti와 다른 UUID], exp=now+REFRESH_EXPIRE }
    │       → 서명: REFRESH_TOKEN_SECRET_KEY (HS256)
    │       → refresh_token 문자열 반환
    │
    ├─ (7) AuthRefreshToken.save(redis, jti=refresh_payload["jti"], user_id, ttl=7일)
    │       → Redis: "auth:refresh:{jti}" = "MEM:xxxx" (TTL=604800초)
    │
    └─ (8) 반환: { access_token, refresh_token, user_id, type: "MEM" }
    │
    ▼
[프론트엔드]
    localStorage.setItem("access_token",  access_token)
    localStorage.setItem("refresh_token", refresh_token)
    localStorage.setItem("user_id",       user_id)
    → 이후 모든 API 요청: Authorization: Bearer {access_token}
```

---

### 3-3. 게스트 로그인 흐름

```
[프론트엔드: api.js → guestLogin()]
    │ POST /api/auth/guest
    │ Body: (없음)
    ▼
[auth_service.guest_login(redis)]
    ├─ (1) uuid = str(uuid4())
    │       user_id = "GST:" + uuid
    │
    ├─ (2) GuestUser(uuid=uuid, created_at=now.isoformat()).save(redis, ttl=24h)
    │       → Redis: "user:GST:{uuid}" = Hash { uuid, created_at, session_id="" }
    │
    ├─ (3) jwt_utils.create_access_token(user_id)  (TTL: ACCESS_EXPIRE)
    │       jwt_utils.create_refresh_token(user_id) (TTL: 24h — MEM의 7일이 아님)
    │
    ├─ (4) AuthRefreshToken.save(redis, jti, user_id, ttl=24h)
    │       → Redis: "auth:refresh:{jti}" = "GST:uuid" (TTL=86400초)
    │
    └─ (5) 반환: { access_token, refresh_token, user_id, type: "GST" }
    │
    ▼
[프론트엔드]
    → PostgreSQL에는 아무것도 저장되지 않음
    → 24시간 내에 활동 없으면 Redis TTL 만료로 자동 소멸
```

---

### 3-4. 인증된 API 요청 흐름 (모든 세션 API)

```
[프론트엔드: api.js]
    │ POST /api/sessions/{session_id}/message
    │ Headers: { Authorization: "Bearer {access_token}" }
    │ Body: { message: "오사카 일정 짜줘" }
    ▼
[Nginx]
    → /api/* → TA_backend:8000 프록시
    ▼
[FastAPI: Dependency get_current_user(token)]
    ├─ oauth2_scheme이 Authorization 헤더에서 token 추출
    │
    ├─ jwt_utils.verify_access_token(token)
    │   ├─ jwt.decode(token, ACCESS_TOKEN_SECRET_KEY, algorithms=["HS256"])
    │   │   실패(만료/변조): HTTPException(401, "토큰 만료 또는 유효하지 않음")
    │   │
    │   ├─ payload["type"] 확인 (선택적 강화)
    │   │   "type"이 없거나 이상하면 HTTPException(401)
    │   │
    │   └─ payload["sub"] = user_id 반환
    │
    └─ user_id ("MEM:abc123" 또는 "GST:uuid") 반환
    ▼
[엔드포인트 함수]
    user_id를 매개변수로 받아 처리
    → 이후 모든 로직에서 "default_user" 대신 실제 user_id 사용

[중요: Access Token은 Redis를 조회하지 않는다]
    → 짧은 만료 시간(15~60분)이 Redis 불필요를 보장
    → Redis 조회를 추가하면 모든 API에 DB round-trip이 생기므로 성능 저하
    → 로그아웃은 Refresh Token만 Redis에서 삭제하면 됨
       (Access Token은 만료까지 유효하나 15~60분이므로 허용 가능한 위험)
```

---

### 3-5. 토큰 갱신 흐름

```
[프론트엔드: api.js]
    401 응답 감지 시 자동으로:
    │ POST /api/auth/refresh
    │ Body: { refresh_token: "..." }
    ▼
[auth_service.refresh_token(redis, refresh_token)]
    ├─ (1) jwt_utils.verify_refresh_token(refresh_token)
    │       → jwt.decode(token, REFRESH_TOKEN_SECRET_KEY, ...)
    │       실패: HTTPException(401, "갱신 토큰 만료")
    │       → payload: { sub=user_id, jti }
    │
    ├─ (2) AuthRefreshToken.load(redis, jti)
    │       → Redis "auth:refresh:{jti}" 조회
    │       None이면: HTTPException(401, "이미 로그아웃된 토큰")
    │       [이것이 Redis의 핵심 역할: 서버 측 무효화]
    │
    ├─ (3) jwt_utils.create_access_token(user_id)
    │       → 새 Access Token 발급 (만료 갱신)
    │
    └─ (4) 반환: { access_token }
    │
    ▼
[프론트엔드]
    localStorage.setItem("access_token", new_access_token)
    → 실패했던 요청을 새 토큰으로 재시도

[Refresh Token 교체 정책]
    - 현재 설계: Refresh Token은 재발급하지 않음 (7일 내 유효)
    - 보안 강화 시: 매 refresh마다 새 Refresh Token 발급 + 이전 jti 삭제 (Rotation)
      → Rotation 적용 시 탈취된 Refresh Token으로 재사용 불가
```

---

### 3-6. 로그아웃 흐름

```
[프론트엔드: account.js]
    │ POST /api/auth/logout
    │ Headers: { Authorization: "Bearer {access_token}" }
    │ Body: { refresh_token: "..." }
    ▼
[auth_service.logout(redis, refresh_token)]
    ├─ (1) jwt_utils.verify_refresh_token(refresh_token) → jti 추출
    │       실패해도 이미 만료된 것이므로 에러 무시하고 성공 반환
    │
    ├─ (2) AuthRefreshToken.delete(redis, jti)
    │       → Redis "auth:refresh:{jti}" 삭제
    │       이후 이 jti로 /refresh 호출 시 무조건 401
    │
    └─ (3) 반환: { status: "success" }
    ▼
[프론트엔드]
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    localStorage.removeItem("user_id")
    → 로그인 화면으로 이동
```

---

### 3-7. 창 닫기(Flush) 흐름

```
[프론트엔드: script.js]
    window.addEventListener('beforeunload', () => {
        navigator.sendBeacon('/api/session/flush',
            JSON.stringify({ session_id: currentSessionId })
        )
        // Authorization 헤더는 sendBeacon에서 설정 불가
        // → 대안: session_id 기반으로 Redis에서 owner 확인 후 처리
    })
    ▼
[facade.py: POST /api/session/flush]
    │ (user_id를 헤더 대신 Redis에서 세션 소유자로 확인)
    ▼
[SessionMeta.load(redis, session_id)]
    │ → owner = "MEM:abc" or "GST:uuid"
    │
    ├─ owner.startswith("GST"):
    │    SessionMeta.delete(redis, session_id)
    │    SessionState.delete(redis, session_id)
    │    UserSessions.remove(redis, user_id, session_id)
    │    GuestUser.load(redis, uuid) → delete()
    │
    └─ MEM/SNS 계열:
         PostgresManager로 sessions 테이블에 upsert:
           { session_id, user_id=owner, title, topic, context, mode, is_manual_title }
         SessionMeta.delete(redis, session_id)
         SessionState.delete(redis, session_id)

[beforeunload 시 sendBeacon 한계]
    → Authorization 헤더 불가 → session_id로 Redis에서 owner 직접 조회
    → CSRF 위험: session_id가 노출되면 타인이 flush 호출 가능
    → 보안 강화: session_id를 서버가 발급한 단기 토큰으로 대체 (Phase 5.5)
```

---

## 4. 구현 단계별 명세

---

### Phase 1 — 유틸리티 구현

**목적:** 이후 모든 단계에서 사용할 JWT·패스워드 도구를 먼저 만든다.

**생성할 파일:**

```
module/
└── auth/
    ├── __init__.py
    ├── jwt_utils.py
    └── password_utils.py
```

---

#### `module/auth/jwt_utils.py`

```python
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from setting.config import (
    ACCESS_TOKEN_SECRET_KEY,
    REFRESH_TOKEN_SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

ALGORITHM = "HS256"


def create_access_token(user_id: str) -> str:
    """
    Access Token 생성.
    서명 키: ACCESS_TOKEN_SECRET_KEY (REFRESH와 다른 값)
    payload: {
        sub:  user_id ("MEM:abc", "GST:uuid"),
        type: user_id.split(":")[0] ("MEM", "GST", ...),
        jti:  str(uuid4()) — 이 토큰 고유 ID (Redis에는 저장 안 함),
        exp:  now + ACCESS_TOKEN_EXPIRE_MINUTES
    }
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  str(uuid.uuid4()),
        "exp":  expire,
    }
    return jwt.encode(payload, ACCESS_TOKEN_SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, ttl_seconds: int = None) -> tuple[str, str]:
    """
    Refresh Token 생성.
    서명 키: REFRESH_TOKEN_SECRET_KEY (ACCESS와 다른 값)
    ttl_seconds: None이면 REFRESH_TOKEN_EXPIRE_DAYS 사용, 게스트는 86400 전달

    반환: (refresh_token_str, jti)
    jti를 함께 반환하는 이유: 호출자가 Redis에 저장할 때 jti가 필요하므로
    payload는 Access Token과 동일 구조 (sub, type, jti, exp)
    """
    now = datetime.now(tz=timezone.utc)
    if ttl_seconds is None:
        ttl_seconds = int(REFRESH_TOKEN_EXPIRE_DAYS) * 24 * 3600
    expire = now + timedelta(seconds=ttl_seconds)
    jti = str(uuid.uuid4())
    payload = {
        "sub":  user_id,
        "type": user_id.split(":")[0],
        "jti":  jti,
        "exp":  expire,
    }
    token = jwt.encode(payload, REFRESH_TOKEN_SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def verify_access_token(token: str) -> dict:
    """
    Access Token 검증 및 payload 반환.
    ACCESS_TOKEN_SECRET_KEY로만 검증 → Refresh Token은 여기서 파싱 실패
    만료 또는 서명 오류 시 HTTPException(401).
    """
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
    """
    Refresh Token 검증 및 payload 반환.
    REFRESH_TOKEN_SECRET_KEY로만 검증 → Access Token은 여기서 파싱 실패
    만료 또는 서명 오류 시 HTTPException(401).
    """
    try:
        payload = jwt.decode(token, REFRESH_TOKEN_SECRET_KEY, algorithms=[ALGORITHM])
        if "sub" not in payload or "jti" not in payload:
            raise HTTPException(status_code=401, detail="유효하지 않은 갱신 토큰")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="갱신 토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 갱신 토큰")
```

**추가할 환경 변수 로드 — `setting/config.py` 하단에 추가:**

```python
# ==========================================
# 5. 인증 설정
# ==========================================
ACCESS_TOKEN_SECRET_KEY    = os.getenv("ACCESS_TOKEN_SECRET_KEY", "")
REFRESH_TOKEN_SECRET_KEY   = os.getenv("REFRESH_TOKEN_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
REFRESH_TOKEN_EXPIRE_DAYS   = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
```

---

#### `module/auth/password_utils.py`

```python
from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """평문 패스워드를 bcrypt로 해시하여 반환."""
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """평문과 해시를 비교하여 일치 여부 반환."""
    return _ctx.verify(plain, hashed)
```

---

### Phase 2 — PostgreSQL 테이블 실체화

**목적:** `postgres_tables.py`에 정의된 ORM 모델을 실제 DB에 생성한다.

**실행할 명령 (프로젝트 루트에서):**

```bash
# TA_db 컨테이너가 실행 중인지 먼저 확인
docker ps | grep TA_db

# 1. 마이그레이션 파일 자동 생성
alembic revision --autogenerate -m "initial schema"

# 2. DB에 실제 적용
alembic upgrade head
```

**완료 조건:**
- `alembic/versions/` 안에 파일이 1개 생성됨
- pgAdmin(포트 5050) 또는 psql로 접속 시 아래 테이블이 존재함:
  - `users`, `user_profile`, `user_security`, `user_oauth`, `user_preference`, `sessions`

**주의:**
- `TA_db` 컨테이너가 실행 중이어야 함
- `.env`의 `DATABASE_URL`이 올바르게 설정되어 있어야 함
- Docker 컨테이너 안에서 실행할 경우: `docker exec -it TA_backend alembic upgrade head`

---

### Phase 3 — Auth 서비스 구현

**목적:** 회원가입·로그인·게스트·토큰 갱신·로그아웃 비즈니스 로직을 구현한다.

**생성할 파일:**

```
module/
└── auth/
    └── auth_service.py
```

---

#### `module/auth/auth_service.py` (전체 구현)

```python
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from module.node.memory.postgres_manager import PostgresManager
from module.node.memory.redis_manager import RedisManager
from module.node.memory.redis_tables import AuthRefreshToken, GuestUser, TTL_GUEST
from module.node.memory.postgres_tables import User, UserProfile, UserSecurity, UserPreference
from module.auth.jwt_utils import (
    create_access_token, create_refresh_token,
    verify_refresh_token,
)
from module.auth.password_utils import hash_password, verify_password


async def signup(postgres: PostgresManager, data: dict) -> dict:
    """
    회원가입.
    data: { username, email, password }

    DB 처리 순서:
    1. email 중복 확인 (user_profile)
    2. user_id 생성 및 4개 테이블 insert

    실패 조건:
    - 이미 가입된 이메일 → HTTPException(409)
    """
    email    = data["email"]
    username = data["username"]
    password = data["password"]

    # 1. 이메일 중복 확인
    existing = await postgres.fetch_one(
        "SELECT user_id FROM user_profile WHERE email = :email",
        {"email": email}
    )
    if existing:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다")

    # 2. user_id 생성
    user_id = "MEM:" + str(uuid.uuid4())

    # 3. 4개 테이블 순차 insert (트랜잭션 보장 필요)
    now = datetime.now(tz=timezone.utc)
    await postgres.execute(
        "INSERT INTO users (user_id, user_type, status, created_at) "
        "VALUES (:user_id, 'MEM', 'active', :created_at)",
        {"user_id": user_id, "created_at": now}
    )
    await postgres.execute(
        "INSERT INTO user_profile (user_id, email, name, nickname, updated_at) "
        "VALUES (:user_id, :email, :name, :nickname, :updated_at)",
        {"user_id": user_id, "email": email, "name": username, "nickname": username, "updated_at": now}
    )
    await postgres.execute(
        "INSERT INTO user_security (user_id, password_hash, login_fail_count) "
        "VALUES (:user_id, :pw_hash, 0)",
        {"user_id": user_id, "pw_hash": hash_password(password)}
    )
    await postgres.execute(
        "INSERT INTO user_preference (user_id, updated_at) VALUES (:user_id, :updated_at)",
        {"user_id": user_id, "updated_at": now}
    )

    return {"user_id": user_id}


async def login(postgres: PostgresManager, redis: RedisManager, id: str, pw: str) -> dict:
    """
    로그인.
    id: 이메일 주소
    pw: 평문 패스워드

    성공 시: { access_token, refresh_token, user_id, type }
    실패 시: HTTPException(401 또는 403)
    """
    # 1. 이메일로 user_id 조회
    row = await postgres.fetch_one(
        "SELECT user_id FROM user_profile WHERE email = :email",
        {"email": id}
    )
    if not row:
        raise HTTPException(status_code=401, detail="존재하지 않는 계정입니다")

    user_id = row["user_id"]

    # 2. 보안 정보 조회
    sec = await postgres.fetch_one(
        "SELECT password_hash, login_fail_count, locked_until "
        "FROM user_security WHERE user_id = :user_id",
        {"user_id": user_id}
    )

    # 3. 계정 잠금 확인
    now = datetime.now(tz=timezone.utc)
    if sec["locked_until"] and sec["locked_until"] > now:
        raise HTTPException(status_code=403, detail="계정이 잠겨 있습니다. 잠시 후 다시 시도하세요")

    # 4. 패스워드 검증
    if not verify_password(pw, sec["password_hash"]):
        fail_count = sec["login_fail_count"] + 1
        if fail_count >= 5:
            locked_until = now.replace(second=0, microsecond=0)  # 30분 후
            from datetime import timedelta
            locked_until = now + timedelta(minutes=30)
            await postgres.execute(
                "UPDATE user_security SET login_fail_count=:cnt, locked_until=:locked "
                "WHERE user_id=:user_id",
                {"cnt": fail_count, "locked": locked_until, "user_id": user_id}
            )
            raise HTTPException(status_code=403, detail="로그인 5회 실패. 계정이 30분간 잠겼습니다")
        await postgres.execute(
            "UPDATE user_security SET login_fail_count=:cnt WHERE user_id=:user_id",
            {"cnt": fail_count, "user_id": user_id}
        )
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다")

    # 5. 로그인 성공 갱신
    await postgres.execute(
        "UPDATE user_security SET last_login_at=:now, login_fail_count=0 WHERE user_id=:user_id",
        {"now": now, "user_id": user_id}
    )

    # 6. 이중키 토큰 발급
    access_token = create_access_token(user_id)
    refresh_token, jti = create_refresh_token(user_id)  # 7일 TTL

    # 7. Redis에 Refresh Token 저장
    await AuthRefreshToken.save(redis, jti, user_id)

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user_id":       user_id,
        "type":          "MEM",
    }


async def guest_login(redis: RedisManager) -> dict:
    """
    게스트 로그인.
    PostgreSQL에는 아무것도 저장하지 않음.
    Refresh Token TTL = 24시간 (일반 회원의 7일이 아님)
    """
    guest_uuid = str(uuid.uuid4())
    user_id    = "GST:" + guest_uuid
    now        = datetime.now(tz=timezone.utc)

    # 1. GuestUser Redis 저장 (TTL 24h)
    guest = GuestUser(uuid=guest_uuid, created_at=now.isoformat())
    await guest.save(redis)

    # 2. 이중키 토큰 발급 (Refresh TTL = 24h)
    access_token = create_access_token(user_id)
    refresh_token, jti = create_refresh_token(user_id, ttl_seconds=TTL_GUEST)

    # 3. Redis에 Refresh Token 저장 (TTL 24h)
    await AuthRefreshToken.save(redis, jti, user_id, ttl=TTL_GUEST)

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user_id":       user_id,
        "type":          "GST",
    }


async def refresh_token_service(redis: RedisManager, refresh_token: str) -> dict:
    """
    토큰 갱신.
    1. REFRESH_TOKEN_SECRET_KEY로 서명 검증
    2. Redis에서 jti 존재 확인 (서버 측 무효화 체크)
    3. 새 Access Token 발급

    Redis에 없는 jti → 로그아웃된 토큰 → 401
    """
    # 1. 서명 검증 (REFRESH 키 사용 — ACCESS 키로 서명된 토큰은 여기서 거부됨)
    payload = verify_refresh_token(refresh_token)
    jti     = payload["jti"]
    user_id = payload["sub"]

    # 2. Redis에서 토큰 존재 확인
    stored_user_id = await AuthRefreshToken.load(redis, jti)
    if stored_user_id is None:
        raise HTTPException(status_code=401, detail="이미 로그아웃된 토큰입니다")

    # 3. 새 Access Token 발급
    new_access_token = create_access_token(user_id)

    return {"access_token": new_access_token}


async def logout(redis: RedisManager, refresh_token: str) -> None:
    """
    로그아웃.
    Refresh Token의 jti를 Redis에서 삭제 → 이후 refresh 요청 불가
    토큰이 이미 만료되었어도 에러 없이 성공 처리.
    """
    try:
        payload = verify_refresh_token(refresh_token)
        jti = payload["jti"]
        await AuthRefreshToken.delete(redis, jti)
    except HTTPException:
        # 이미 만료된 토큰이어도 로그아웃은 성공 처리
        pass
```

---

### Phase 4 — FastAPI 미들웨어 (Dependency)

**목적:** 모든 인증 필요 엔드포인트에서 JWT를 자동으로 검증하고 user_id를 주입한다.

**생성할 파일:**

```
module/
└── auth/
    └── dependencies.py
```

#### `module/auth/dependencies.py`

```python
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from module.auth.jwt_utils import verify_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Authorization: Bearer {token} 헤더에서 user_id를 추출하여 반환.

    - Access Token을 ACCESS_TOKEN_SECRET_KEY로 검증
    - Refresh Token을 여기 끼워도 다른 키라 파싱 실패 → 401
    - 토큰이 없거나 만료된 경우 HTTPException(401)

    반환: user_id 문자열 ("MEM:abc123", "GST:uuid" 등)
    """
    payload = verify_access_token(token)
    return payload["sub"]


async def get_current_member(user_id: str = Depends(get_current_user)) -> str:
    """
    게스트(GST)를 허용하지 않는 엔드포인트용.
    user_id가 GST로 시작하면 HTTPException(403).

    사용 예: 개인 설정 저장, 세션 이름 변경 등 회원 전용 기능
    """
    if user_id.startswith("GST"):
        raise HTTPException(status_code=403, detail="게스트는 이 기능을 사용할 수 없습니다")
    return user_id


async def get_optional_user(request: Request) -> str | None:
    """
    인증 선택적 엔드포인트용. 토큰 없어도 None 반환 (에러 없음).
    사용 예: 공개 페이지, 공유 세션 보기 등
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        payload = verify_access_token(token)
        return payload["sub"]
    except HTTPException:
        return None
```

---

### Phase 5 — facade.py 실제 연결

**목적:** 현재 Mock DB로 동작하는 `facade.py`를 실제 PostgreSQL + Redis로 교체한다.

#### 5-1. lifespan으로 매니저 인스턴스 초기화

```python
# facade.py 상단에 추가
from contextlib import asynccontextmanager
from module.node.memory.postgres_manager import PostgresManager
from module.node.memory.redis_manager import RedisManager
from module.auth.dependencies import get_current_user, get_current_member
from module.auth import auth_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 DB 연결 초기화
    app.state.postgres = PostgresManager()
    app.state.redis    = RedisManager()
    yield
    # 앱 종료 시 Redis 커넥션 풀 반환
    await app.state.redis.close()

# app = FastAPI(...)를 아래로 교체
app = FastAPI(title="TravelArchive API", lifespan=lifespan)
```

#### 5-2. Auth 엔드포인트 교체

| 엔드포인트 | 현재 | 변경 후 |
|-----------|------|---------|
| `POST /api/auth/signup` | Mock 응답 반환 | `auth_service.signup()` 호출 |
| `POST /api/auth/login` | Mock 응답 반환 | `auth_service.login()` 호출 |
| `POST /api/auth/guest` | Mock 응답 반환 | `auth_service.guest_login()` 호출 |
| `POST /api/auth/refresh` | 없음 (신규) | `auth_service.refresh_token_service()` 호출 |
| `POST /api/auth/logout` | 없음 (신규) | `auth_service.logout()` 호출 |

```python
# 교체 예시

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

@app.post("/api/auth/signup")
async def signup(req: SignUpRequest, request: Request):
    postgres = request.app.state.postgres
    result = await auth_service.signup(postgres, {
        "username": req.username, "email": req.email, "password": req.password
    })
    return {"status": "success", **result}

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    postgres = request.app.state.postgres
    redis    = request.app.state.redis
    return await auth_service.login(postgres, redis, req.id, req.pw)

@app.post("/api/auth/guest")
async def guest_login(request: Request):
    redis = request.app.state.redis
    return await auth_service.guest_login(redis)

@app.post("/api/auth/refresh")
async def refresh(req: RefreshRequest, request: Request):
    redis = request.app.state.redis
    return await auth_service.refresh_token_service(redis, req.refresh_token)

@app.post("/api/auth/logout")
async def logout(req: LogoutRequest, request: Request):
    redis = request.app.state.redis
    await auth_service.logout(redis, req.refresh_token)
    return {"status": "success"}
```

#### 5-3. 세션 엔드포인트에 user_id 주입

```python
# 모든 세션 관련 엔드포인트에 Dependency 추가
from fastapi import Depends

@app.get("/api/sessions")
async def get_session_list(
    mode: str = "personal",
    request: Request = None,
    user_id: str = Depends(get_current_user)   # ← 추가
):
    redis    = request.app.state.redis
    postgres = request.app.state.postgres
    # UserSessions.get_all(redis, user_id) → session_id 목록
    # 각 session_id로 SessionMeta.load() → title, mode 조회
    # mode 필터링 후 반환

@app.post("/api/sessions")
async def create_session(
    req: SessionCreateRequest,
    request: Request = None,
    user_id: str = Depends(get_current_user)   # ← 추가
):
    # "default_user" 대신 실제 user_id 사용
    # SessionMeta를 Redis에 저장
    # UserSessions.add(redis, user_id, session_id)
    ...

@app.post("/api/sessions/{session_id}/message")
async def send_message(
    session_id: str,
    req: MessageRequest,
    request: Request = None,
    user_id: str = Depends(get_current_user)   # ← 추가
):
    # SessionContainer에 user_id 전달
    # Redis에서 세션 소유자 확인 후 접근 제한
    ...
```

#### 5-4. Flush 엔드포인트 추가

```python
class FlushRequest(BaseModel):
    session_id: str

@app.post("/api/session/flush")
async def flush_session(req: FlushRequest, request: Request):
    """
    프론트엔드 beforeunload 이벤트가 navigator.sendBeacon으로 호출.
    Authorization 헤더 없음 → Redis에서 세션 소유자 직접 확인.
    """
    redis    = request.app.state.redis
    postgres = request.app.state.postgres
    session_id = req.session_id

    meta = await SessionMeta.load(redis, session_id)
    if not meta:
        return {"status": "not_found"}

    if meta.owner.startswith("GST"):
        await SessionMeta.delete(redis, session_id)
        await SessionState.delete(redis, session_id)
        await UserSessions.remove(redis, meta.owner, session_id)
    else:
        await postgres.execute(
            "INSERT INTO sessions (session_id, user_id, title, topic, context, mode, is_manual_title) "
            "VALUES (:sid, :uid, :title, :topic, :ctx, :mode, :manual) "
            "ON CONFLICT (session_id) DO UPDATE SET "
            "title=EXCLUDED.title, topic=EXCLUDED.topic, context=EXCLUDED.context, "
            "mode=EXCLUDED.mode, is_manual_title=EXCLUDED.is_manual_title, updated_at=now()",
            {
                "sid": session_id, "uid": meta.owner,
                "title": meta.title, "topic": meta.topic,
                "ctx": meta.context, "mode": meta.mode,
                "manual": meta.is_manual_title == "true"
            }
        )
        await SessionMeta.delete(redis, session_id)
        await SessionState.delete(redis, session_id)

    return {"status": "flushed"}
```

#### 5-5. Mock DB 제거 대상

아래 전역 변수들을 모두 제거하고 실제 DB 호출로 교체:

```python
# 제거 대상
active_sessions: Dict[str, SessionContainer]   # → Redis SessionMeta/SessionState
mock_sessions_db                               # → PostgreSQL sessions 테이블 + Redis
mock_chat_history_db                           # → PostgreSQL (별도 테이블 추가 필요)
mock_session_meta_db                           # → PostgreSQL sessions 테이블
mock_trip_ranges                               # → PostgreSQL (trip_ranges 테이블 추가 필요)
mock_memos                                     # → PostgreSQL (memos 테이블 추가 필요)
mock_plans                                     # → PostgreSQL (plans 테이블 추가 필요)
mock_map_markers                               # → PostgreSQL (map_markers 테이블 추가 필요)
```

> **주의:** `mock_trip_ranges`, `mock_memos`, `mock_plans`, `mock_map_markers`는 현재
> `postgres_tables.py`에 테이블이 없음. Phase 5 진행 전에 해당 테이블을 추가하고
> Alembic 마이그레이션 필요.

**추가해야 할 테이블 (postgres_tables.py에 append):**

```python
class ChatMessage(Base):
    """채팅 메시지 영구 저장."""
    __tablename__ = "chat_messages"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    role       = Column(String(10), nullable=False)   # "user" / "bot"
    content    = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

class TripRange(Base):
    """세션별 여행 기간 설정."""
    __tablename__ = "trip_ranges"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    start_date = Column(String(10), nullable=False)   # "YYYY-MM-DD"
    end_date   = Column(String(10), nullable=False)

class Memo(Base):
    """날짜별 메모."""
    __tablename__ = "memos"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    date_key   = Column(String(10), nullable=False)   # "YYYY-MM-DD"
    content    = Column(Text, nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("session_id", "date_key", name="uq_memo_session_date"),)

class Plan(Base):
    """날짜별 여행 일정."""
    __tablename__ = "plans"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    date_key   = Column(String(10), nullable=False)
    items      = Column(JSONB, nullable=True)   # [{"time": "09:00", "activity": "도착"}]
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("session_id", "date_key", name="uq_plan_session_date"),)

class MapMarker(Base):
    """지도 마커."""
    __tablename__ = "map_markers"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    marker_id  = Column(String(50), nullable=False)
    lat        = Column(Float, nullable=False)
    lng        = Column(Float, nullable=False)
    title      = Column(String(255), nullable=True)
    __table_args__ = (UniqueConstraint("session_id", "marker_id", name="uq_marker_session_id"),)
```

---

### Phase 6 — 프론트엔드 토큰 연동

**목적:** `api.js`가 토큰을 저장하고, 모든 요청에 Authorization 헤더를 붙이고, 401 시 자동 갱신하도록 한다.

**수정할 파일:** `frontend/src/js/api.js`

#### 6-1. 토큰 저장/조회 유틸

```javascript
// api.js 최상단에 추가
const TokenStore = {
    getAccess:    () => localStorage.getItem("access_token"),
    getRefresh:   () => localStorage.getItem("refresh_token"),
    setAccess:    (t) => localStorage.setItem("access_token",  t),
    setRefresh:   (t) => localStorage.setItem("refresh_token", t),
    setUserId:    (id) => localStorage.setItem("user_id", id),
    getUserId:    () => localStorage.getItem("user_id"),
    clear:        () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user_id");
    },
};
```

#### 6-2. 공통 fetch 래퍼 (자동 갱신 포함)

```javascript
// api.js에 추가: 모든 인증 요청에 사용
let isRefreshing = false;
let refreshQueue = [];  // 갱신 중 대기 중인 요청들

async function authFetch(url, options = {}) {
    const token = TokenStore.getAccess();
    const headers = {
        "Content-Type": "application/json",
        ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        ...(options.headers || {}),
    };

    let response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
        // Access Token 만료 → Refresh Token으로 갱신 시도
        if (!isRefreshing) {
            isRefreshing = true;
            try {
                const refreshRes = await fetch("/api/auth/refresh", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ refresh_token: TokenStore.getRefresh() }),
                });
                if (!refreshRes.ok) {
                    // Refresh도 실패 → 로그아웃
                    TokenStore.clear();
                    window.location.href = "/";  // 로그인 화면으로
                    return;
                }
                const { access_token } = await refreshRes.json();
                TokenStore.setAccess(access_token);
                isRefreshing = false;
                // 대기 중인 요청들 재시도
                refreshQueue.forEach(fn => fn(access_token));
                refreshQueue = [];
            } catch (e) {
                isRefreshing = false;
                TokenStore.clear();
                window.location.href = "/";
                return;
            }
        } else {
            // 이미 갱신 중 → 갱신 완료 후 재시도 대기
            await new Promise(resolve => refreshQueue.push(resolve));
        }

        // 새 토큰으로 원래 요청 재시도
        const newToken = TokenStore.getAccess();
        const newHeaders = { ...headers, "Authorization": `Bearer ${newToken}` };
        response = await fetch(url, { ...options, headers: newHeaders });
    }

    return response;
}
```

#### 6-3. 로그인/게스트 함수 수정

```javascript
// 기존 login 함수를 아래로 교체
async login(id, pw) {
    const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, pw }),
    });
    if (!res.ok) throw new Error("로그인 실패");
    const data = await res.json();
    // 토큰 저장
    TokenStore.setAccess(data.access_token);
    TokenStore.setRefresh(data.refresh_token);
    TokenStore.setUserId(data.user_id);
    return data;
},

// 기존 guestLogin 함수를 아래로 교체
async guestLogin() {
    const res = await fetch("/api/auth/guest", { method: "POST" });
    const data = await res.json();
    TokenStore.setAccess(data.access_token);
    TokenStore.setRefresh(data.refresh_token);
    TokenStore.setUserId(data.user_id);
    return data;
},
```

#### 6-4. 기존 API 함수들을 authFetch로 교체

```javascript
// 예: fetchSessionList (기존 fetch → authFetch로 교체)
async fetchSessionList(mode = "personal") {
    const res = await authFetch(`/api/sessions?mode=${mode}`);
    return res.json();
},

// 예: sendMessage (스트리밍 — Authorization 헤더 수동 추가)
async sendMessage(sessionId, message) {
    const token = TokenStore.getAccess();
    const res = await fetch(`/api/sessions/${sessionId}/message`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ message }),
    });
    return res;  // 스트리밍은 호출자가 response.body.getReader() 처리
},
```

#### 6-5. beforeunload flush 추가

```javascript
// script.js에 추가
window.addEventListener('beforeunload', () => {
    const sessionId = getCurrentSessionId();  // 현재 열린 세션 ID
    if (!sessionId) return;
    navigator.sendBeacon(
        '/api/session/flush',
        new Blob(
            [JSON.stringify({ session_id: sessionId })],
            { type: 'application/json' }
        )
    );
});
```

---

### Phase 7 — SNS OAuth 연동

**목적:** 카카오·네이버·구글 소셜 로그인을 구현한다.

**주의:** 각 provider의 앱 등록 및 콜백 URL 설정이 선행되어야 함.

**흐름:**

```
[프론트엔드] /api/auth/social/{provider} 클릭
    ↓
[백엔드] provider OAuth 인증 URL로 리다이렉트
    ↓
[provider] 사용자 인증
    ↓
[백엔드] /api/auth/social/{provider}/callback
    ├─ provider로부터 access_token 수령
    ├─ provider API로 사용자 정보(provider_sub) 조회
    ├─ user_oauth 테이블에서 (provider, provider_sub) 검색
    │    ├─ 존재: 기존 user_id 사용
    │    └─ 없음: 신규 user_id 생성 후 users + user_oauth insert
    └─ JWT 이중키 발급 후 프론트엔드로 리다이렉트
         → URL 파라미터에 access_token, refresh_token 포함
         → 프론트엔드에서 TokenStore에 저장
```

**생성할 파일:**
```
module/
└── auth/
    └── oauth_service.py
```

---

## 5. 파일 구조 최종 목표

```
module/
└── auth/
    ├── __init__.py
    ├── jwt_utils.py          ← Phase 1: 이중키 토큰 생성/검증
    ├── password_utils.py     ← Phase 1: bcrypt 해시
    ├── auth_service.py       ← Phase 3: 회원가입/로그인/게스트/갱신/로그아웃
    ├── dependencies.py       ← Phase 4: FastAPI Dependency
    └── oauth_service.py      ← Phase 7: SNS OAuth
```

---

## 6. 환경 변수 체크리스트

`Phase 1` 시작 전 `.env`에 반드시 설정되어야 할 값:

```
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASS}@TA_db:5432/${POSTGRES_DB}
REDIS_URL=redis://:${REDIS_PASSWORD}@TA_redis:6379/${REDIS_DB_INDEX}

# 이중키: 반드시 서로 다른 값 사용 (openssl rand -hex 32 로 생성)
ACCESS_TOKEN_SECRET_KEY=      ← 랜덤 256bit 이상 문자열
REFRESH_TOKEN_SECRET_KEY=     ← ACCESS와 다른 별도 키 (같으면 이중키 의미 없음)

ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## 7. 단계별 완료 조건 요약

| Phase | 완료 조건 |
|-------|---------|
| 1 | `jwt_utils` 단위 테스트: Access 키로 Refresh Token 파싱 시 오류 발생 확인 |
| 2 | pgAdmin에서 6개 테이블 확인 가능 |
| 3 | Postman으로 signup → login → access_token 수령, Refresh Token으로 /refresh 성공 확인 |
| 4 | 인증 헤더 없이 세션 API 호출 시 401 반환 확인; Refresh Token으로 /api/sessions 호출 시 401 확인 |
| 5 | 서버 재시작 후에도 세션 목록이 유지됨 확인 |
| 6 | 프론트엔드 로그인 후 모든 API가 토큰 포함하여 호출됨 확인; 401 시 자동 갱신 확인 |
| 7 | 소셜 로그인 후 JWT 이중키 발급 및 DB 저장 확인 |

---

## 8. 의존성 그래프

```
Phase 1 (이중키 유틸리티)
    │
    ├──────────────────────────┐
    ▼                          ▼
Phase 2 (DB 테이블)       Phase 3 (Auth 서비스)
    │                          │
    └──────────┬───────────────┘
               ▼
          Phase 4 (FastAPI Dependency)
               │
               ▼
          Phase 5 (facade 연결 — Mock 제거)
               │
               ▼
          Phase 6 (프론트엔드 토큰 연동)
               │
               ▼
          Phase 7 (SNS OAuth)
```

Phase 2와 Phase 3은 병렬 진행 가능.
Phase 4는 반드시 Phase 1, 3 완료 후 진행.
Phase 5는 Phase 2, 4 완료 후 진행.
Phase 6는 Phase 5 완료 후 진행 (백엔드가 실제 토큰을 발급해야 연동 가능).

---

## 9. 보안 고려사항

### 9-1. 현재 설계의 보안 강점

| 위협 | 대응 |
|------|------|
| Access Token 탈취 | 만료 15~60분 — 짧은 유효 기간으로 피해 최소화 |
| Refresh Token 탈취 | Redis 저장 + 로그아웃 시 즉시 삭제 → 서버 측 무효화 |
| 토큰 혼용 공격 | 이중키: Access 키로 Refresh 검증 불가, 반대도 불가 |
| 무차별 대입 | 로그인 5회 실패 시 30분 잠금 |

### 9-2. 개선 가능한 보안 강화 옵션 (Phase 7 이후)

- **Refresh Token Rotation**: 매 refresh마다 새 Refresh Token 발급 + 이전 jti 삭제
  → 탈취된 Refresh Token이 한 번 사용되면 원래 사용자가 재갱신 시 실패 → 즉시 감지
- **HTTPS 필수**: Nginx에서 이미 certbot/Let's Encrypt 설정됨 (certified.conf)
- **HttpOnly Cookie**: `access_token`을 localStorage 대신 HttpOnly 쿠키에 저장
  → XSS로 토큰 탈취 불가 (CSRF 방어도 함께 필요)
- **CORS 강화**: `facade.py`의 `allow_origins=["*"]`를 실제 도메인으로 제한
