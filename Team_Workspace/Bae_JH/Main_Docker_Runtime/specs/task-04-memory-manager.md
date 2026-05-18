# task-04: MemoryManager + Execute Unit 인터페이스 분리

## 목표

실행 단위(Execute Unit)는 DB를 전혀 모른다.
Cacher(Redis 읽기/쓰기)와 MemoryManager(이벤트 emit)만 사용한다.
MemoryManager가 백그라운드에서 Redis ↔ PG 동기화를 전담한다.

---

## 현재 상태

- `execute_unit/user.py`: Cacher만 사용 ✓ (task-03 완료)
- `execute_unit/system.py`: Cacher만 사용 ✓ (task-03 완료)
- `execute_unit/auth.py`: Loader 직접 호출 — 변경 필요
- `execute_unit/chat.py`: postgres 직접 수신 — 이번 task 범위 밖 (task-05)
- `execute_unit/widget.py`: redis 직접 수신 ✓ (변경 없음)
- `memory/manager.py`: 존재하지 않음 — 신규 생성
- `memory/events.py`: 존재하지 않음 — 신규 생성

---

## Deliverables

### 1. `backend/memory/events.py` (신규)

이벤트 타입 dataclass 정의. 로직 없음.

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoginEvent:
    user_id: str

@dataclass
class LogoutEvent:
    user_id: str

@dataclass
class SignupEvent:
    user_id: str

@dataclass
class BeforeUnloadEvent:
    user_id: str

@dataclass
class SessionOpenEvent:
    session_id: str
    user_id: str

@dataclass
class SessionBlurEvent:
    session_id: str
    user_id: str

@dataclass
class WidgetChangeEvent:
    session_id: str
    widget_type: str   # "markers" | "routes" | "ranges"

@dataclass
class CacheMissEvent:
    resource: str      # "user_profile" | "session_meta" | "ui_settings"
    user_id: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class AccountDeleteEvent:
    user_id: str
```

---

### 2. `backend/memory/manager.py` (신규)

MemoryManager 클래스. 싱글톤 인스턴스 1개.

규칙:
- `start(postgres, redis)` → asyncio background task 시작
- `stop()` → task 취소
- `emit(event)` → fire-and-forget (put_nowait)
- `emit_and_wait(event)` → flush처럼 완료 보장이 필요할 때
- 큐가 60초 idle → `_idle_sweep()` 자동 실행
- 각 핸들러 예외는 삼켜서 로그만 — 루프 죽으면 안 됨

```python
import asyncio
import json
from typing import Any

from .events import (
    LoginEvent, LogoutEvent, SignupEvent, BeforeUnloadEvent,
    SessionOpenEvent, SessionBlurEvent, WidgetChangeEvent,
    CacheMissEvent, AccountDeleteEvent,
)
from .cacher import Cacher
from .loader import Loader

SWEEP_INTERVAL = 60.0   # idle_sweep 주기 (초)


class MemoryManager:

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._pg  = None
        self._redis = None

    # ── 앱 생명주기 ──────────────────────────────────────────

    async def start(self, postgres: Any, redis: Any) -> None:
        self._pg    = postgres
        self._redis = redis
        self._task  = asyncio.create_task(self._loop(), name="MemoryManager")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── Execute Unit 인터페이스 ───────────────────────────────

    def emit(self, event: object) -> None:
        """fire-and-forget. execute unit이 호출하는 유일한 인터페이스."""
        self._queue.put_nowait({"event": event, "done": None})

    async def emit_and_wait(self, event: object) -> None:
        """응답 전에 완료 보장이 필요한 경우 (logout 등)."""
        done = asyncio.Event()
        self._queue.put_nowait({"event": event, "done": done})
        await done.wait()

    # ── 내부 루프 ─────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(
                    self._queue.get(), timeout=SWEEP_INTERVAL
                )
                done: asyncio.Event | None = item["done"]
                try:
                    await self._dispatch(item["event"])
                except Exception as e:
                    print(f"[MemoryManager] 핸들러 오류: {e}")
                finally:
                    if done:
                        done.set()
            except asyncio.TimeoutError:
                try:
                    await self._idle_sweep()
                except Exception as e:
                    print(f"[MemoryManager] idle_sweep 오류: {e}")
            except asyncio.CancelledError:
                break

    async def _dispatch(self, event: object) -> None:
        match event:
            case LoginEvent():        await self._on_login(event)
            case LogoutEvent():       await self._on_logout(event)
            case SignupEvent():        await self._on_signup(event)
            case BeforeUnloadEvent(): await self._on_beforeunload(event)
            case SessionOpenEvent():  await self._on_session_open(event)
            case SessionBlurEvent():  await self._on_session_blur(event)
            case WidgetChangeEvent(): await self._on_widget_change(event)
            case CacheMissEvent():    await self._on_cache_miss(event)
            case AccountDeleteEvent(): await self._on_account_delete(event)
            case _:
                print(f"[MemoryManager] 알 수 없는 이벤트: {type(event)}")

    # ── 이벤트 핸들러 ─────────────────────────────────────────

    async def _on_login(self, e: LoginEvent) -> None:
        # PG → Redis warm (best-effort)
        await Loader.load_user_to_redis(e.user_id, self._pg, self._redis)

    async def _on_logout(self, e: LogoutEvent) -> None:
        # Redis → PG flush → Redis 정리
        await Loader.flush_user_data(e.user_id, self._pg, self._redis)
        from ..system.flush_service import FlushService
        await FlushService.flush_user_sessions(e.user_id, self._pg, self._redis)
        await Cacher.delete_user_data(e.user_id, self._redis)

    async def _on_signup(self, e: SignupEvent) -> None:
        # 신규 가입 시 빈 프로필 Redis 초기화 (optional warm)
        await Cacher.save_user_profile(e.user_id, {}, self._redis)

    async def _on_beforeunload(self, e: BeforeUnloadEvent) -> None:
        # 5초 제한 best-effort flush
        try:
            async with asyncio.timeout(5.0):
                await Loader.flush_user_data(e.user_id, self._pg, self._redis)
                from ..system.flush_service import FlushService
                await FlushService.flush_user_sessions(e.user_id, self._pg, self._redis)
        except TimeoutError:
            print(f"[MemoryManager] beforeunload flush 타임아웃: {e.user_id}")

    async def _on_session_open(self, e: SessionOpenEvent) -> None:
        # 세션 메타 Redis hit 확인, miss 시 PG에서 warm
        meta = await Cacher.get_session_meta(e.session_id, self._redis)
        if not meta:
            await Loader.load_session_to_redis(e.session_id, self._pg, self._redis)

    async def _on_session_blur(self, e: SessionBlurEvent) -> None:
        # dirty 위젯 선택적 flush
        await Loader.flush_dirty_widgets(e.session_id, self._pg, self._redis)

    async def _on_widget_change(self, e: WidgetChangeEvent) -> None:
        # dirty 플래그만 표시 (실제 데이터는 Cacher가 이미 Redis에 저장)
        await self._redis.execute({
            "action": "sadd",
            "key":    f"session:{e.session_id}:dirty_widgets",
            "member": e.widget_type,
        })

    async def _on_cache_miss(self, e: CacheMissEvent) -> None:
        # 단건 재적재
        if e.resource == "user_profile" and e.user_id:
            await Loader.load_user_to_redis(e.user_id, self._pg, self._redis)
        elif e.resource == "session_meta" and e.session_id:
            await Loader.load_session_to_redis(e.session_id, self._pg, self._redis)

    async def _on_account_delete(self, e: AccountDeleteEvent) -> None:
        # pending_delete 플래그 확인 후 PG 상태 변경 + Redis 정리
        if await Cacher.is_account_deleted(e.user_id, self._redis):
            await self._pg.execute({
                "action": "update", "model": "User",
                "filters": {"user_id": e.user_id},
                "data": {"status": "deleted"},
            })
        await Cacher.delete_user_data(e.user_id, self._redis)

    async def _idle_sweep(self) -> None:
        # dirty 상태인 세션 일괄 flush
        result = await self._redis.execute({
            "action": "scan",
            "pattern": "session:*:dirty_widgets",
        })
        for key in result.get("data", []):
            # key 형식: "session:{session_id}:dirty_widgets"
            parts = key.split(":")
            if len(parts) == 3:
                session_id = parts[1]
                try:
                    await Loader.flush_dirty_widgets(session_id, self._pg, self._redis)
                except Exception as e:
                    print(f"[MemoryManager] sweep flush 실패 {session_id}: {e}")
```

---

### 3. `backend/memory/loader.py` 추가 메서드

기존 파일에 아래 3개 메서드 추가 (클래스 끝에).

**3-A. `load_session_to_redis`**
```python
@staticmethod
async def load_session_to_redis(session_id: str, postgres, redis) -> None:
    """세션 open 시 PG → Redis. 세션 메타 + 위젯 적재."""
    from ..memory.cacher import Cacher
    info = await Loader.get_session_info(postgres, session_id)
    if not info:
        return
    meta = {
        "name":            info.get("title", ""),
        "topic":           info.get("topic", ""),
        "context":         info.get("context_summary", ""),
        "is_manual_title": str(info.get("is_manual_title", False)).lower(),
    }
    await Cacher.cache_session_meta(session_id, meta, redis)
```

**3-B. `flush_dirty_widgets`**
```python
@staticmethod
async def flush_dirty_widgets(session_id: str, postgres, redis) -> None:
    """dirty_widgets Set에 표시된 위젯만 선택적으로 PG에 내림."""
    from ..memory.cacher import Cacher
    result = await redis.execute({
        "action": "smembers",
        "key":    f"session:{session_id}:dirty_widgets",
    })
    dirty: set = set(result.get("data", []))
    if not dirty:
        return

    if "markers" in dirty:
        markers = await Cacher.get_markers(session_id, redis)
        # markers는 위젯 노드가 관리 — DB 스키마 없음, Redis 전용 (skip PG)
        dirty.discard("markers")

    if "ranges" in dirty:
        ranges = await Cacher.get_ranges(session_id, redis)
        # ranges도 위젯 노드 관리 — Redis 전용 (skip PG)
        dirty.discard("ranges")

    if "meta" in dirty:
        from ..system.flush_service import FlushService
        await FlushService.flush_single_session(session_id, postgres, redis)
        dirty.discard("meta")

    # 처리된 항목 dirty Set 제거
    await redis.execute({"action": "delete", "key": f"session:{session_id}:dirty_widgets"})
```

**3-C. `fetch_user_profile`** (Cacher cache-miss fallback용)
```python
@staticmethod
async def fetch_user_profile(user_id: str, postgres) -> dict:
    """Cacher cache miss 시 PG에서 단건 조회. re-warm은 Cacher가 담당."""
    result = await postgres.execute({
        "action":  "read",
        "model":   "UserProfile",
        "filters": {"user_id": user_id},
    })
    rows = result.get("data", [])
    if not rows:
        return {}
    p = rows[0]
    return {
        "nickname":       p.get("nickname", ""),
        "bio":            p.get("bio", ""),
        "email1":         p.get("email", ""),
        "extra_contacts": p.get("extra_contacts") or [],
    }
```

---

### 4. `backend/memory/cacher.py` 변경

`get_user_profile` 시그니처에 optional `postgres` 추가, miss 시 fallback.

```python
@staticmethod
async def get_user_profile(user_id: str, redis, postgres=None) -> dict:
    result = await redis.execute({
        "action": "hgetall",
        "key":    f"user:{user_id}:profile",
    })
    data = result.get("data", {}) or {}
    if data:
        return data
    # cache miss
    if postgres is None:
        return {}
    from .loader import Loader
    data = await Loader.fetch_user_profile(user_id, postgres)
    if data:
        await Cacher.save_user_profile(user_id, data, redis)
    return data
```

`get_ui_settings` 동일 패턴 (optional postgres, miss → `Loader.get_settings` 조회):

```python
@staticmethod
async def get_ui_settings(user_id: str, redis, postgres=None) -> dict:
    result = await redis.execute({
        "action": "get",
        "key":    f"user:{user_id}:ui_settings",
    })
    val = result.get("value")
    if val:
        try:
            return json.loads(val)
        except Exception:
            pass
    # cache miss
    if postgres is None:
        return {}
    from .loader import Loader
    full = await Loader.get_settings(postgres, user_id)
    ui = full.get("data") or {}
    if ui:
        await Cacher.save_ui_settings(user_id, ui, redis)
    return ui
```

나머지 get_user_style, get_user_travel은 miss 시 빈 dict 반환 (최초 설정 전 정상).

---

### 5. `backend/execute_unit/auth.py` 변경

AuthUnit은 auth 생명주기 PG 작업(Loader 호출)을 유지한다.
단, login/logout/signup 성공 후 MemoryManager에 이벤트를 emit한다.

시그니처에 `manager` 추가.

```python
from typing import Any, Optional
from ..memory.loader import Loader
from ..memory.events import LoginEvent, LogoutEvent, SignupEvent


class AuthUnit:

    @staticmethod
    async def signup(postgres: Any, data: dict, manager: Any) -> Any:
        result = await Loader.signup(postgres, data)
        if result.get("user_id"):
            manager.emit(SignupEvent(user_id=result["user_id"]))
        return result

    @staticmethod
    async def login(postgres: Any, redis: Any, user_id: str, password: str, manager: Any) -> Any:
        result = await Loader.login(postgres, redis, user_id, password)
        if result.get("user_id"):
            manager.emit(LoginEvent(user_id=result["user_id"]))
        return result

    @staticmethod
    async def refresh_token(redis: Any, refresh_token: str) -> Any:
        return await Loader.refresh_token(redis, refresh_token)

    @staticmethod
    async def logout(postgres: Any, redis: Any, refresh_token: str,
                     user_id: Optional[str], manager: Any) -> Any:
        if user_id:
            await manager.emit_and_wait(LogoutEvent(user_id=user_id))
        return await Loader.logout(postgres, redis, refresh_token, user_id)

    @staticmethod
    async def get_my_info(postgres: Any, user_id: str) -> Any:
        return await Loader.get_my_info(postgres, user_id)
```

주의: logout은 `emit_and_wait` — flush 완료 후 token revoke.

---

### 6. `backend/memory/loader.py` lifespan 변경

MemoryManager 인스턴스를 lifespan에서 시작하고 `app.state.manager`에 주입.

```python
# lifespan yield 직전에 추가:
from .manager import MemoryManager
manager = MemoryManager()
await manager.start(postgres, redis)
app.state.manager = manager

# yield 이후 (종료 시):
await manager.stop()
```

---

### 7. `backend/facade.py` 변경

`manager` 주입이 필요한 엔드포인트만 수정.

```python
# signup
return await AuthUnit.signup(
    request.app.state.postgres, {"email": ..., ...}, request.app.state.manager)

# login
return await AuthUnit.login(
    request.app.state.postgres, request.app.state.redis, req.id, req.pw,
    request.app.state.manager)

# logout
await AuthUnit.logout(
    request.app.state.postgres, request.app.state.redis,
    req.refresh_token, user_id, request.app.state.manager)
return {"status": "success", "message": "로그아웃 되었습니다"}

# logout_all_devices — 동일 패턴

# flush_sessions (beforeunload)
request.app.state.manager.emit(BeforeUnloadEvent(user_id=user_id))
return {"status": "success"}
```

flush_sessions 엔드포인트는 SystemUnit.flush_user_sessions 호출 대신
manager.emit(BeforeUnloadEvent)로 교체.

---

## Gemini Evaluation Checklist

1. `memory/events.py` 존재 + 9개 이벤트 dataclass 정의?
2. `memory/manager.py` 존재 + MemoryManager 클래스 + `emit`/`emit_and_wait`/`start`/`stop` 메서드?
3. `manager._loop`가 asyncio.TimeoutError 시 `_idle_sweep` 호출?
4. `manager._dispatch`가 모든 이벤트 타입 처리?
5. `memory/loader.py`에 `load_session_to_redis`/`flush_dirty_widgets`/`fetch_user_profile` 추가?
6. `memory/loader.py` lifespan에서 MemoryManager 시작 + `app.state.manager` 주입?
7. `memory/cacher.py`의 `get_user_profile`/`get_ui_settings`에 optional postgres + miss fallback?
8. `execute_unit/auth.py`가 manager 인자 수신 + login/logout/signup 후 이벤트 emit?
9. `execute_unit/auth.py`의 logout이 `emit_and_wait` 사용?
10. `facade.py`의 auth 엔드포인트가 `request.app.state.manager` 전달?
11. `facade.py`의 flush_sessions가 `BeforeUnloadEvent` emit으로 교체?
12. spec에 없는 기능 추가 없음?

## Response Language
Korean
