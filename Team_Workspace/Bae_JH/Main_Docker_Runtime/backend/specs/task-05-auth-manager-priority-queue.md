# task-05: AuthUnit DB 독립 + MemoryManager Priority Queue

## 목표

1. AuthUnit이 Loader/postgres를 완전히 모른다.
   auth 요청도 asyncio.Future 기반 이벤트로 manager에 위임한다.
2. MemoryManager에 priority_queue를 추가한다.
   auth 요청(login/logout/signup/refresh)은 priority queue로,
   기존 lifecycle 이벤트(warm/flush/sweep)는 event queue로 분리된다.
   priority queue는 event queue보다 항상 먼저 처리된다.

---

## 현재 상태

- `execute_unit/auth.py`: Loader 직접 import, postgres 인자 수신
- `memory/manager.py`: 단일 asyncio.Queue, emit/emit_and_wait 단일 경로
- `memory/events.py`: lifecycle 이벤트만 존재, auth 요청 이벤트 없음
- `facade.py`: auth 엔드포인트가 postgres, redis, manager를 모두 전달

---

## Deliverables

### 1. `backend/memory/events.py` 변경

기존 9개 이벤트 유지. 아래 5개 auth 요청 이벤트 추가.
`asyncio.Future` 필드: 결과 반환 채널 (manager가 set_result/set_exception).

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


# ── 기존 이벤트 (변경 없음) ───────────────────────────────────
# LoginEvent, LogoutEvent, SignupEvent, BeforeUnloadEvent,
# SessionOpenEvent, SessionBlurEvent, WidgetChangeEvent,
# CacheMissEvent, AccountDeleteEvent

# ── 신규: Auth 요청 이벤트 (Future 기반, priority queue 전용) ──

@dataclass
class LoginRequestEvent:
    user_id:  str
    password: str
    future:   asyncio.Future

@dataclass
class LogoutRequestEvent:
    """flush + token revoke를 한 번에 처리. LogoutEvent(background)와 별개."""
    refresh_token: str
    user_id:       Optional[str]
    future:        asyncio.Future

@dataclass
class SignupRequestEvent:
    data:   dict
    future: asyncio.Future

@dataclass
class RefreshRequestEvent:
    refresh_token: str
    future:        asyncio.Future

@dataclass
class GetMyInfoRequestEvent:
    user_id: str
    future:  asyncio.Future
```

---

### 2. `backend/memory/manager.py` 변경

**2-A. 큐 분리**

`__init__`에 `_priority_queue` 추가.

```python
def __init__(self) -> None:
    self._priority_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    self._event_queue:    asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    self._task: asyncio.Task[None] | None = None
    self._pg:    Any = None
    self._redis: Any = None
```

**2-B. emit / emit_and_wait 시그니처 변경**

`priority: bool = False` 파라미터 추가.

```python
def emit(self, event: object, priority: bool = False) -> None:
    """fire-and-forget."""
    queue = self._priority_queue if priority else self._event_queue
    queue.put_nowait({"event": event, "done": None})

async def emit_and_wait(self, event: object, priority: bool = False) -> None:
    """완료 보장."""
    done = asyncio.Event()
    queue = self._priority_queue if priority else self._event_queue
    queue.put_nowait({"event": event, "done": done})
    await done.wait()
```

**2-C. _loop 변경**

priority_queue를 먼저 확인한 뒤 event_queue를 대기한다.

```python
async def _loop(self) -> None:
    while True:
        try:
            # priority 먼저 (non-blocking check)
            try:
                item = self._priority_queue.get_nowait()
            except asyncio.QueueEmpty:
                # priority 없으면 event_queue 대기 (timeout = sweep 주기)
                item = await asyncio.wait_for(
                    self._event_queue.get(), timeout=SWEEP_INTERVAL
                )
            done: asyncio.Event | None = item["done"]
            try:
                await self._dispatch(item["event"])
            except Exception as e:
                print(f"[MemoryManager] 핸들러 오류: {e}")
                # Future 기반 이벤트면 예외를 future에 전파
                ev = item["event"]
                if hasattr(ev, "future") and not ev.future.done():
                    ev.future.set_exception(e)
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
```

**2-D. _dispatch에 5개 핸들러 추가**

```python
async def _dispatch(self, event: object) -> None:
    match event:
        # ── 기존 (변경 없음) ──────────────────────────────
        case LoginEvent():         await self._on_login(event)
        case LogoutEvent():        await self._on_logout(event)
        case SignupEvent():        await self._on_signup(event)
        case BeforeUnloadEvent():  await self._on_beforeunload(event)
        case SessionOpenEvent():   await self._on_session_open(event)
        case SessionBlurEvent():   await self._on_session_blur(event)
        case WidgetChangeEvent():  await self._on_widget_change(event)
        case CacheMissEvent():     await self._on_cache_miss(event)
        case AccountDeleteEvent(): await self._on_account_delete(event)
        # ── 신규: auth 요청 ───────────────────────────────
        case LoginRequestEvent():   await self._on_login_request(event)
        case LogoutRequestEvent():  await self._on_logout_request(event)
        case SignupRequestEvent():  await self._on_signup_request(event)
        case RefreshRequestEvent(): await self._on_refresh_request(event)
        case GetMyInfoRequestEvent(): await self._on_get_my_info_request(event)
        case _:
            print(f"[MemoryManager] 알 수 없는 이벤트: {type(event)}")
```

**2-E. auth 요청 핸들러 5개 추가**

```python
async def _on_login_request(self, e: LoginRequestEvent) -> None:
    try:
        result = await Loader.login(self._pg, self._redis, e.user_id, e.password)
        # 로그인 성공 시 Redis warm (background로 추가 — non-blocking)
        if result.get("user_id"):
            self.emit(LoginEvent(user_id=result["user_id"]))
        e.future.set_result(result)
    except Exception as ex:
        e.future.set_exception(ex)

async def _on_logout_request(self, e: LogoutRequestEvent) -> None:
    try:
        if e.user_id:
            await Loader.flush_user_data(e.user_id, self._pg, self._redis)
            from ..system.flush_service import FlushService
            await FlushService.flush_user_sessions(e.user_id, self._pg, self._redis)
            await Cacher.delete_user_data(e.user_id, self._redis)
        await Loader.logout(self._pg, self._redis, e.refresh_token)
        e.future.set_result(None)
    except Exception as ex:
        e.future.set_exception(ex)

async def _on_signup_request(self, e: SignupRequestEvent) -> None:
    try:
        result = await Loader.signup(self._pg, e.data)
        if result.get("user_id"):
            self.emit(SignupEvent(user_id=result["user_id"]))
        e.future.set_result(result)
    except Exception as ex:
        e.future.set_exception(ex)

async def _on_refresh_request(self, e: RefreshRequestEvent) -> None:
    try:
        result = await Loader.refresh_token(self._redis, e.refresh_token)
        e.future.set_result(result)
    except Exception as ex:
        e.future.set_exception(ex)

async def _on_get_my_info_request(self, e: GetMyInfoRequestEvent) -> None:
    try:
        result = await Loader.get_my_info(self._pg, e.user_id)
        e.future.set_result(result)
    except Exception as ex:
        e.future.set_exception(ex)
```

---

### 3. `backend/execute_unit/auth.py` 전체 재작성

Loader import 없음. postgres 인자 없음. redis는 get_my_info에서 Cacher 조회용으로만 사용.

```python
# [역할] 인증 생명주기를 담당하는 실행 단위.
#        DB를 전혀 모른다. 모든 auth 작업은 manager의 priority queue를 통해 위임한다.
#        asyncio.Future로 결과를 동기적으로 수신하므로 응답 지연 없음.
#
#        호출 방향: facade → AuthUnit → manager.emit(XxxRequestEvent, priority=True) → Future 대기
import asyncio
from typing import Any, Optional

from ..memory.cacher import Cacher
from ..memory.events import (
    GetMyInfoRequestEvent,
    LoginRequestEvent,
    LogoutRequestEvent,
    RefreshRequestEvent,
    SignupRequestEvent,
)


class AuthUnit:

    @staticmethod
    async def signup(data: dict, manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(SignupRequestEvent(data=data, future=future), priority=True)
        return await future

    @staticmethod
    async def login(user_id: str, password: str, manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(LoginRequestEvent(user_id=user_id, password=password, future=future), priority=True)
        return await future

    @staticmethod
    async def refresh_token(refresh_token: str, manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(RefreshRequestEvent(refresh_token=refresh_token, future=future), priority=True)
        return await future

    @staticmethod
    async def logout(refresh_token: str, user_id: Optional[str], manager: Any) -> Any:
        future = asyncio.get_running_loop().create_future()
        manager.emit(
            LogoutRequestEvent(refresh_token=refresh_token, user_id=user_id, future=future),
            priority=True,
        )
        return await future

    @staticmethod
    async def get_my_info(user_id: str, redis: Any, manager: Any) -> Any:
        # Redis에 있으면 즉시 반환
        profile = await Cacher.get_user_profile(user_id, redis)
        if profile:
            return {
                "status":    "success",
                "user_id":   user_id,
                "user_type": user_id.split(":")[0],
                "nickname":  profile.get("nickname", ""),
                "email":     profile.get("email1", profile.get("email", "")),
            }
        # miss → manager를 통해 PG 조회
        future = asyncio.get_running_loop().create_future()
        manager.emit(GetMyInfoRequestEvent(user_id=user_id, future=future), priority=True)
        return await future
```

---

### 4. `backend/facade.py` 변경

auth 엔드포인트 시그니처 수정. postgres/redis 제거 (manager만 전달).
단, get_my_info는 redis + manager 둘 다 전달.

```python
# signup
return await AuthUnit.signup(
    {"email": req.email, "password": req.password, "nickname": req.nickname},
    request.app.state.manager,
)

# login
return await AuthUnit.login(req.id, req.pw, request.app.state.manager)

# refresh
return await AuthUnit.refresh_token(req.refresh_token, request.app.state.manager)

# logout (두 엔드포인트 모두)
return await AuthUnit.logout(req.refresh_token, user_id, request.app.state.manager)

# get_my_info
return await AuthUnit.get_my_info(user_id, request.app.state.redis, request.app.state.manager)
```

---

## Gemini Evaluation Checklist

1. `events.py`에 5개 auth 요청 이벤트 존재? (LoginRequestEvent, LogoutRequestEvent, SignupRequestEvent, RefreshRequestEvent, GetMyInfoRequestEvent)
2. 각 auth 요청 이벤트에 `asyncio.Future` 필드 존재?
3. `manager.py`에 `_priority_queue`와 `_event_queue` 두 개 존재?
4. `emit`/`emit_and_wait`에 `priority: bool = False` 파라미터 추가?
5. `_loop`가 priority_queue를 get_nowait()으로 먼저 확인 후 event_queue 대기?
6. `_dispatch`에 5개 auth 요청 핸들러 case 추가?
7. `_on_login_request`: Loader.login 호출 후 future.set_result, 성공 시 LoginEvent emit?
8. `_on_logout_request`: flush_user_data + flush_sessions + delete_user_data + Loader.logout 순서?
9. `execute_unit/auth.py`에 Loader import 없음? postgres 인자 없음?
10. `execute_unit/auth.py`의 모든 메서드가 Future 생성 후 priority=True emit?
11. `execute_unit/auth.py`의 get_my_info가 Cacher 먼저 조회 후 miss 시 manager?
12. `facade.py`의 auth 엔드포인트에서 postgres 제거, manager만 전달?
13. spec에 없는 기능 추가 없음?

## Response Language
Korean
