---
task_id: 03
slug: execute-unit-redis-first
status: implementing
attempts: 0
depends_on: [task-02]
---

# Goal
Execute Unit (UserUnit, SystemUnit)을 DB 완전 독립으로 전환.
모든 사용자·설정 데이터는 Redis(Cacher)에 먼저 저장하고,
DB 접근은 Loader가 생명주기(로그인/로그아웃/플러시)에서만 담당한다.

흐름: Execute Unit → Cacher(Redis) ← → Loader(PostgreSQL)

# Context / Inputs / Outputs

Base path: `/home/pi/NAS/1_TravelArchive_Dev/TravelArchive/Team_Workspace/Bae_JH/Main_Docker_Runtime`

현재 문제:
- `UserUnit`이 postgres에 직접 접근
- `SystemUnit`이 `Loader.get_settings()`, `Loader.update_settings()`를 통해 postgres 접근
- Execute Unit 내부에 SQL 로직 존재

목표:
- Execute Unit은 redis만 받고 Cacher만 호출
- postgres 인자, import 자체를 Execute Unit에서 제거
- Cacher에 사용자 데이터 Redis 메서드 추가
- Loader에 DB↔Redis 동기화(load/flush) 메서드 추가 및 login/logout에 연결

**수정할 파일 5개:**
```
backend/memory/cacher.py         (메서드 추가)
backend/memory/loader.py         (메서드 추가 + login/logout 수정)
backend/execute_unit/user.py     (postgres 제거, Cacher 호출로 교체)
backend/execute_unit/system.py   (postgres 제거, Cacher 호출로 교체)
backend/facade.py                (user/system 엔드포인트 시그니처 수정)
```

# Constraints
- Python 3.10+, 타입 힌트 필수
- Execute Unit 파일에 postgres 인자 및 DB import 완전 제거
- Cacher 메서드는 redis 인자만 받음 (postgres 인자 없음)
- Loader는 기존 DB 로직을 유지하되 load/flush 메서드 추가
- 기존 응답 포맷(JSON 키 이름) 변경 금지 — 프론트와의 계약
- spec에 없는 기능 추가 금지

# Hard Rules
- UserUnit, SystemUnit에 `postgres` 인자, DB import, DB execute 호출 없음
- Cacher 내 새 메서드 시그니처: `(user_id: str, ..., redis) → ...`
- facade.py에서 user/system 관련 엔드포인트는 `request.app.state.redis`를 전달

---

# Deliverables (경로: `/tmp/codex-out-03/`)

## 1. backend/memory/cacher.py

기존 파일 전체 유지하고, 클래스 끝에 아래 메서드 추가.

**Redis Key 구조 (추가):**
```
user:{user_id}:profile      → Hash  (nickname, bio, extra_contacts)
user:{user_id}:style        → String(JSON)
user:{user_id}:travel       → String(JSON)
user:{user_id}:ui_settings  → String(JSON)
user:{user_id}:pending_delete → String('1')
```

**TTL 상수 추가:**
```python
USER_DATA_TTL = 3600 * 8   # 8시간
```

**추가 메서드 (모두 Cacher 클래스 staticmethod):**

```python
# ── 사용자 프로필 ────────────────────────────────────────────
save_user_profile(user_id: str, data: dict, redis) -> None
    # HSET user:{user_id}:profile  (data의 각 key-value, 값은 str 변환)
    # EXPIRE USER_DATA_TTL

get_user_profile(user_id: str, redis) -> dict
    # HGETALL user:{user_id}:profile → dict (없으면 {})

# ── 사용자 스타일 ─────────────────────────────────────────────
save_user_style(user_id: str, data: dict, redis) -> None
    # GET user:{user_id}:style → existing (JSON, 없으면 {})
    # existing.update(data)
    # SET user:{user_id}:style = JSON(merged), TTL=USER_DATA_TTL

get_user_style(user_id: str, redis) -> dict
    # GET user:{user_id}:style → JSON parse, 없으면 {}

# ── 여행 취향 ─────────────────────────────────────────────────
save_user_travel(user_id: str, data: dict, redis) -> None
    # GET user:{user_id}:travel → existing (JSON, 없으면 {})
    # existing.update(data)
    # SET user:{user_id}:travel = JSON(merged), TTL=USER_DATA_TTL

get_user_travel(user_id: str, redis) -> dict
    # GET user:{user_id}:travel → JSON parse, 없으면 {}

# ── UI 설정 ──────────────────────────────────────────────────
save_ui_settings(user_id: str, data: dict, redis) -> None
    # GET user:{user_id}:ui_settings → existing (JSON, 없으면 {})
    # deep-merge: existing[k] = data[k] for each k
    #   단, existing[k]와 data[k] 둘 다 dict면 existing[k].update(data[k])
    # SET user:{user_id}:ui_settings = JSON(merged), TTL=USER_DATA_TTL

get_ui_settings(user_id: str, redis) -> dict
    # GET user:{user_id}:ui_settings → JSON parse, 없으면 {}

# ── 계정 삭제 플래그 ─────────────────────────────────────────
mark_account_deleted(user_id: str, redis) -> None
    # SET user:{user_id}:pending_delete = '1', TTL=USER_DATA_TTL

is_account_deleted(user_id: str, redis) -> bool
    # GET user:{user_id}:pending_delete → '1'이면 True, 없으면 False

# ── 사용자 데이터 전체 삭제 (flush 후 정리) ─────────────────
delete_user_data(user_id: str, redis) -> None
    # DELETE: profile, style, travel, ui_settings, pending_delete 키 5개
```

## 2. backend/memory/loader.py

기존 파일 전체를 출력하되, 아래 수정 적용:

### 2-A. `login()` 메서드에 load_user_to_redis 호출 추가

기존 login 메서드 마지막 return 직전에 추가:
```python
await Loader.load_user_to_redis(user_id_result, postgres, redis)
```
단, `user_id_result`는 auth_service.login()이 반환하는 dict에서 `user_id` 키로 꺼낸 값.
auth_service.login() 반환값 구조: `{"access_token": ..., "refresh_token": ..., "user_id": ...}`
login 메서드 안에서 result를 변수로 받아 user_id를 꺼내어 load 후 result 반환.

### 2-B. `logout()` 메서드에 flush_user_data 호출 추가

기존 logout에서 FlushService.flush_user_sessions 호출 후, 아래 추가:
```python
await Loader.flush_user_data(user_id, postgres, redis)
```

### 2-C. 새 메서드 2개 추가 (Loader 클래스에)

```python
@staticmethod
async def load_user_to_redis(user_id: str, postgres, redis) -> None:
    """로그인 시 DB → Redis. 사용자 데이터를 Cacher에 적재."""
    from ..memory.cacher import Cacher
    # 1) user_profile + user_preferences JOIN 조회
    #    SQL: Loader.get_settings의 SELECT 재활용
    result = await Loader.get_settings(postgres, user_id)
    # 2) profile → Cacher.save_user_profile
    profile = result.get("profile", {})
    if profile:
        await Cacher.save_user_profile(user_id, profile, redis)
    # 3) style → Cacher.save_user_style
    style = result.get("style") or {}
    if style:
        await Cacher.save_user_style(user_id, style, redis)
    # 4) travel → Cacher.save_user_travel
    travel = result.get("travel") or {}
    if travel:
        await Cacher.save_user_travel(user_id, travel, redis)
    # 5) ui_settings → Cacher.save_ui_settings
    ui = result.get("data") or {}
    if ui:
        await Cacher.save_ui_settings(user_id, ui, redis)

@staticmethod
async def flush_user_data(user_id: str, postgres, redis) -> None:
    """로그아웃/플러시 시 Redis → DB. Cacher에서 읽어 DB에 저장 후 Redis 정리."""
    import json
    from datetime import datetime, timezone
    from ..memory.cacher import Cacher

    # 1) pending_delete 확인 → DB 업데이트
    if await Cacher.is_account_deleted(user_id, redis):
        await postgres.execute({
            "action": "update", "model": "User",
            "filters": {"user_id": user_id},
            "data": {"status": "deleted"},
        })

    # 2) profile flush
    profile = await Cacher.get_user_profile(user_id, redis)
    if profile:
        profile_data = {k: v for k, v in profile.items()
                        if k in ("nickname", "bio", "extra_contacts")}
        if profile_data:
            profile_data["updated_at"] = datetime.now(timezone.utc)
            await postgres.execute({
                "action": "update", "model": "UserProfile",
                "filters": {"user_id": user_id},
                "data": profile_data,
            })

    # 3) style flush
    style = await Cacher.get_user_style(user_id, redis)
    if style:
        await postgres.execute({
            "action": "raw_sql",
            "sql": """
                INSERT INTO user_preferences (user_id, style, updated_at)
                VALUES (:uid, CAST(:style AS jsonb), NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET style = COALESCE(user_preferences.style,'{}') || CAST(:style AS jsonb),
                    updated_at = NOW()
            """,
            "params": {"uid": user_id, "style": json.dumps(style)},
        })

    # 4) travel flush
    travel = await Cacher.get_user_travel(user_id, redis)
    if travel:
        await postgres.execute({
            "action": "raw_sql",
            "sql": """
                INSERT INTO user_preferences (user_id, travel, updated_at)
                VALUES (:uid, CAST(:travel AS jsonb), NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET travel = COALESCE(user_preferences.travel,'{}') || CAST(:travel AS jsonb),
                    updated_at = NOW()
            """,
            "params": {"uid": user_id, "travel": json.dumps(travel)},
        })

    # 5) ui_settings flush
    ui = await Cacher.get_ui_settings(user_id, redis)
    if ui:
        await postgres.execute({
            "action": "raw_sql",
            "sql": """
                INSERT INTO user_preferences (user_id, ui_settings, updated_at)
                VALUES (:uid, CAST(:ui AS jsonb), NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET ui_settings = COALESCE(user_preferences.ui_settings,'{}') || CAST(:ui AS jsonb),
                    updated_at = NOW()
            """,
            "params": {"uid": user_id, "ui": json.dumps(ui)},
        })

    # 6) Redis 정리
    await Cacher.delete_user_data(user_id, redis)
    print(f"[Loader] {user_id} 사용자 데이터 플러시 완료")
```

## 3. backend/execute_unit/user.py

전체 재작성. postgres 인자·import 없음. redis만 받음.

```python
from typing import Any, Optional
from ..memory.cacher import Cacher


class UserUnit:

    @staticmethod
    async def get_account_info(redis: Any, user_id: Optional[str]) -> dict:
        if not user_id:
            return {"status": "unauthenticated", "user_id": None}
        profile = await Cacher.get_user_profile(user_id, redis)
        return {
            "status":    "success",
            "user_id":   user_id,
            "user_type": user_id.split(":")[0],
            "nickname":  profile.get("nickname", ""),
            "email":     profile.get("email1", profile.get("email", "")),
        }

    @staticmethod
    async def save_profile(user_id: str, data: dict, redis: Any) -> dict:
        await Cacher.save_user_profile(user_id, data, redis)
        return {"status": "success"}

    @staticmethod
    async def save_style(user_id: str, data: dict, redis: Any) -> dict:
        await Cacher.save_user_style(user_id, data, redis)
        return {"status": "success"}

    @staticmethod
    async def save_travel(user_id: str, data: dict, redis: Any) -> dict:
        await Cacher.save_user_travel(user_id, data, redis)
        return {"status": "success"}

    @staticmethod
    async def delete_account(user_id: str, redis: Any) -> dict:
        await Cacher.mark_account_deleted(user_id, redis)
        return {"status": "success", "message": "계정이 삭제되었습니다"}
```

## 4. backend/execute_unit/system.py

전체 재작성. postgres 인자·import 없음. redis만 받음 (flush는 예외: FlushService 유지).

```python
import random
from datetime import date
from typing import Any, Optional

from ..memory.cacher import Cacher
from ..system.flush_service import FlushService


class SystemUnit:

    # ── 세션 플러시 (redis + postgres 필요 — 예외 허용) ─────────
    @staticmethod
    async def flush_user_sessions(user_id: str, postgres: Any, redis: Any) -> Any:
        return await FlushService.flush_user_sessions(user_id, postgres, redis)

    # ── 앱 설정 (Redis only) ─────────────────────────────────
    @staticmethod
    async def get_settings(redis: Any, user_id: str) -> dict:
        ui      = await Cacher.get_ui_settings(user_id, redis)
        profile = await Cacher.get_user_profile(user_id, redis)
        style   = await Cacher.get_user_style(user_id, redis)
        travel  = await Cacher.get_user_travel(user_id, redis)
        return {
            "status":  "success",
            "data":    ui,
            "profile": {
                "bio":            profile.get("bio"),
                "nickname":       profile.get("nickname"),
                "email1":         profile.get("email1", profile.get("email")),
                "extra_contacts": profile.get("extra_contacts") or [],
            },
            "style":  style,
            "travel": travel,
        }

    @staticmethod
    async def update_settings(user_id: str, settings: dict, redis: Any) -> dict:
        await Cacher.save_ui_settings(user_id, settings, redis)
        return {"status": "success"}

    @staticmethod
    async def get_context(redis: Any, user_id: Optional[str]) -> dict:
        defaults = {
            "appGlassOpacity":        "20",
            "leftSidebarCustomWidth":  300,
            "rightSidebarCustomWidth": 300,
            "theme":                  "default",
            "appFontKey":             "pretendard",
            "appFontSize":            15,
            "notifications": {
                "response": False,
                "weather":  False,
                "festival": False,
            },
        }
        if user_id:
            saved = await Cacher.get_ui_settings(user_id, redis)
            for k in ("appGlassOpacity", "leftSidebarCustomWidth", "rightSidebarCustomWidth",
                      "theme", "appFontKey", "appFontSize"):
                if k in saved:
                    defaults[k] = saved[k]
            if isinstance(saved.get("notifications"), dict):
                defaults["notifications"].update(saved["notifications"])
        return {
            "today":    date.today().isoformat(),
            "settings": defaults,
        }

    @staticmethod
    async def save_theme(user_id: Optional[str], theme: str, redis: Any) -> dict:
        if user_id:
            await Cacher.save_ui_settings(user_id, {"theme": theme}, redis)
        return {"status": "success"}

    # ── 정적 응답 ─────────────────────────────────────────────
    @staticmethod
    def get_help() -> dict:
        return {"status": "success", "data": "도움말 가이드라인 페이지입니다."}

    @staticmethod
    def get_weather() -> dict:
        selected = random.choice(["clear", "cloudy", "rain", "night"])
        return {
            "type": selected,
            "params": {
                "intensity":     round(random.uniform(0.2, 1.5), 2),
                "windDirection": round(random.uniform(-1.0, 1.0), 2),
                "cloudDensity":  random.randint(3, 10),
                "starDensity":   random.randint(100, 300),
            },
        }
```

## 5. backend/facade.py

기존 파일 전체 출력하되, 아래 엔드포인트 본문만 수정.
나머지는 변경 없음.

**수정 대상 엔드포인트 (redis 전달로 변경):**

```python
# get_account_info
return await UserUnit.get_account_info(request.app.state.redis, user_id)

# save_user_profile
return await UserUnit.save_profile(user_id, data, request.app.state.redis)

# save_user_style
return await UserUnit.save_style(user_id, data, request.app.state.redis)

# save_travel_preferences
return await UserUnit.save_travel(user_id, data, request.app.state.redis)

# delete_account
return await UserUnit.delete_account(user_id, request.app.state.redis)

# get_app_context
return await SystemUnit.get_context(request.app.state.redis, user_id)

# get_settings
return await SystemUnit.get_settings(request.app.state.redis, user_id)

# update_settings  (인자 순서 변경: user_id, settings, redis)
return await SystemUnit.update_settings(user_id, settings, request.app.state.redis)

# save_theme_preference
return await SystemUnit.save_theme(user_id, req.theme, request.app.state.redis)
```

---

# Gemini Evaluation Checklist

1. `cacher.py`에 USER_DATA_TTL 상수 존재?
2. `cacher.py`에 save_user_profile/get_user_profile 메서드 존재?
3. `cacher.py`에 save_user_style/save_user_travel/save_ui_settings 메서드 존재?
4. `cacher.py`에 mark_account_deleted/is_account_deleted/delete_user_data 메서드 존재?
5. `loader.py`에 load_user_to_redis/flush_user_data 메서드 존재?
6. `loader.py`의 login()에서 load_user_to_redis 호출?
7. `loader.py`의 logout()에서 flush_user_data 호출?
8. `execute_unit/user.py`에 postgres 인자 또는 DB 관련 import 없음?
9. `execute_unit/system.py`에 Loader 및 postgres 인자 없음? (flush_user_sessions 제외)
10. `facade.py`의 user/system 엔드포인트가 redis를 전달?
11. spec에 없는 기능 추가 없음?

# Response Language
Korean
