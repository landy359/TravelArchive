---
task_id: 02
slug: backend-framework-refactor
status: merged
attempts: 1
depends_on: []
---

# Goal
백엔드 틀 리팩토링: 상세일정(plan)/메모(memo) 제거 + execute_unit/ + memory/cacher.py 계층 도입.
기존 비즈니스 로직은 내부에서 그대로 유지. 구조(폴더/임포트)만 변경.

# Context / Inputs / Outputs

Base path: `/home/pi/NAS/1_TravelArchive_Dev/TravelArchive/Team_Workspace/Bae_JH/Main_Docker_Runtime`

**현재 구조:**
```
backend/
├── facade.py
├── auth/ (그대로 유지)
├── loader/loader.py
├── router/ (그대로 유지)
└── system/
    ├── chat_service.py
    ├── db_interface.py
    ├── session_container.py  (그대로 유지)
    ├── session_cache.py      (→ memory/cacher.py로 대체)
    ├── flush_service.py
    └── team_service.py       (그대로 유지)
```

**목표 구조:**
```
backend/
├── facade.py                 (수정)
├── auth/ (변경 없음)
├── loader/loader.py          (수정: memo_node/plan_node 제거)
├── router/ (변경 없음)
├── system/
│   ├── chat_service.py       (수정: SessionCache → Cacher import)
│   ├── db_interface.py       (변경 없음)
│   ├── session_container.py  (변경 없음)
│   ├── flush_service.py      (수정: SessionCache → Cacher import)
│   └── team_service.py       (변경 없음)
├── execute_unit/             (신규)
│   ├── __init__.py
│   ├── auth.py
│   ├── system.py
│   ├── user.py
│   ├── chat.py
│   └── widget.py
└── memory/                   (신규)
    ├── __init__.py
    └── cacher.py
```

# Constraints
- Python 3.10+, 타입 힌트 필수
- 기존 로직 변경 금지 — 파일 이동/임포트 경로 변경만
- execute_unit 각 클래스는 staticmethod 패턴 유지 (기존 Loader, ChatService와 동일 스타일)
- 절대 경로 기반 임포트 사용 (상대 임포트: `from ..memory.cacher import Cacher`)

# Hard Rules
- spec에 없는 기능 추가 금지
- 외부 라이브러리 신규 추가 금지
- `session_container.py`, `db_interface.py`, `team_service.py`, `auth/` 내부 파일 수정 금지

---

# Deliverables

모든 파일은 `/tmp/codex-out-02/` 기준 상대 경로로 출력.

## 1. backend/memory/__init__.py
빈 파일.

## 2. backend/memory/cacher.py
`system/session_cache.py` 에서 아래만 제거하고 클래스명을 `Cacher`로 변경:
- `save_memo` 메서드 삭제
- `get_memo` 메서드 삭제
- `save_plan` 메서드 삭제
- `get_plan` 메서드 삭제
- `get_indicators` 메서드 삭제

유지: TTL 상수, mark_active, unmark_active, get_active_session_ids,
       set_current_session, get_current_session,
       cache_session_meta, get_session_meta, delete_session_cache,
       save_markers, get_markers, save_routes, get_routes,
       save_ranges, get_ranges

## 3. backend/execute_unit/__init__.py
빈 파일.

## 4. backend/execute_unit/auth.py
클래스명: `AuthUnit`
아래 메서드를 정의. 각 메서드 본문은 기존 `Loader` 또는 `auth/` 모듈을 그대로 호출:
- `signup(postgres, data: dict)`  → `Loader.signup(postgres, data)`
- `login(postgres, redis, user_id: str, password: str)` → `Loader.login(postgres, redis, user_id, password)`
- `refresh_token(redis, refresh_token: str)` → `Loader.refresh_token(redis, refresh_token)`
- `logout(postgres, redis, refresh_token: str, user_id: Optional[str])` → `Loader.logout(postgres, redis, refresh_token, user_id)`
- `get_my_info(postgres, user_id: str)` → `Loader.get_my_info(postgres, user_id)`

## 5. backend/execute_unit/system.py
클래스명: `SystemUnit`
아래 메서드:
- `flush_user_sessions(user_id: str, postgres, redis)` → `FlushService.flush_user_sessions(user_id, postgres, redis)`
- `get_settings(postgres, user_id: str)` → `Loader.get_settings(postgres, user_id)`
- `update_settings(postgres, user_id: str, settings: dict)` → `Loader.update_settings(postgres, user_id, settings)`

## 6. backend/execute_unit/user.py
클래스명: `UserUnit`
아래 메서드 (stub — body는 `pass`만, return None):
- `save_profile(user_id: str, data: dict, postgres) -> None`
- `save_style(user_id: str, data: dict, postgres) -> None`
- `save_travel(user_id: str, data: dict, postgres) -> None`
- `delete_account(user_id: str, postgres) -> None`

각 메서드 첫 줄에 주석: `# TODO: move logic from facade.py`

## 7. backend/execute_unit/chat.py
클래스명: `ChatUnit`
아래 메서드. 각 본문은 `ChatService.*` 를 그대로 호출:
- `send_temp_message(temp_session_id: str, message: str)` → `ChatService.send_temp_message(...)`
- `get_session_list(trip_id, user_id: str, postgres)` → `ChatService.get_session_list(...)`
- `create_session(first_message: str, mode, user_id: str, trip_id, postgres, redis)` → `ChatService.create_session(...)`
- `delete_session(session_id: str, user_id: str, postgres, redis)` → `ChatService.delete_session(...)`
- `leave_session(session_id: str, user_id: str, postgres, redis)` → `ChatService.leave_session(...)`
- `convert_to_personal(session_id: str, user_id: str, postgres, redis)` → `ChatService.convert_to_personal(...)`
- `update_session_title(session_id: str, title: str, user_id: str, postgres, redis)` → `ChatService.update_session_title(...)`
- `update_session_color(session_id: str, color: str, user_id: str, postgres)` → `ChatService.update_session_color(...)`
- `invite_user(session_id: str, invitee: str, user_id: str, postgres)` → `ChatService.invite_user(...)`
- `send_message(session_id: str, message: str, user_id: str, postgres, redis)` → `ChatService.send_message(...)`
- `get_chat_history(session_id: str, postgres, limit: int, offset: int)` → `ChatService.get_chat_history(...)`
- `subscribe_session_events(session_id: str, user_id: str)` → `ChatService.subscribe_session_events(...)`
- `subscribe_user_notifications(user_id: str)` → `ChatService.subscribe_user_notifications(...)`
- `broadcast_typing(session_id: str, user_id: str, postgres)` → `ChatService.broadcast_typing(...)`
- `download_chat(session_id: str, postgres)` → `ChatService.download_chat(...)`
- `upload_files(session_id: str, files, user_id: str, postgres)` → `ChatService.upload_files(...)`
- `share_chat(session_id: str, user_id: str)` → `ChatService.share_chat(...)`

## 8. backend/execute_unit/widget.py
클래스명: `WidgetUnit`
아래 메서드. 본문은 `request.app.state.*_node.*` 패턴 대신 실제 node를 인자로 받아 호출:
- `add_marker(map_node, session_id: str, marker_id: str, lat: float, lng: float, title: str)`
- `delete_marker(map_node, session_id: str, marker_id: str)`
- `set_markers(map_node, session_id: str, markers: list)`
- `get_markers(map_node, session_id: str)`
- `set_routes(map_node, session_id: str, marker_ids: list)`
- `get_routes(map_node, session_id: str)`
- `set_trip_range(trip_range_node, session_id: str, ranges: list)`
- `get_trip_range(trip_range_node, session_id: str)`

각 메서드 본문은 해당 node의 메서드 직접 호출. 예:
  `return await map_node.add_marker(session_id, marker_id, lat, lng, title)`

## 9. backend/loader/loader.py (수정)
현재 파일에서 아래 4줄만 제거하고 나머지는 완전히 동일하게 출력:
```python
from module.node.widget.memo_node      import MemoNode
from module.node.widget.plan_node      import PlanNode
...
memo_node       = MemoNode()
plan_node       = PlanNode()
...
for node in (memo_node, plan_node, map_node, trip_range_node):
    node.bind_redis(redis)
...
app.state.memo_node       = memo_node
app.state.plan_node       = plan_node
```
즉 lifespan 내부에서 map_node, trip_range_node만 남기고 memo_node, plan_node 관련 5줄(import 2 + 생성 2 + state 할당 2)을 제거.
for loop는 `for node in (map_node, trip_range_node):`로 변경.

## 10. backend/system/flush_service.py (수정)
`from .session_cache import SessionCache` → `from ..memory.cacher import Cacher`
`SessionCache.` → `Cacher.` (전체 치환)

## 11. backend/system/chat_service.py (수정)
`from .session_cache import SessionCache` → `from ..memory.cacher import Cacher`
`SessionCache.` → `Cacher.` (전체 치환)
`save_memo`, `get_memo`, `save_plan`, `get_plan` staticmethod 4개 삭제.

## 12. backend/facade.py (수정)
아래 변경 사항 적용. 나머지는 완전히 동일:

**삭제할 것:**
- `MemoRequest` Pydantic 모델 삭제
- `PlanRequest` Pydantic 모델 삭제
- `PUT /api/sessions/{session_id}/memo` 엔드포인트 (save_memo) 삭제
- `GET /api/sessions/{session_id}/memo` 엔드포인트 (get_memo) 삭제
- `PUT /api/sessions/{session_id}/plan` 엔드포인트 (save_plan) 삭제
- `GET /api/sessions/{session_id}/plan` 엔드포인트 (get_plan) 삭제
- `GET /api/sessions/{session_id}/indicators` 엔드포인트 삭제
- 상단 주석에서 "메모·플래너" 언급 제거

**추가/수정할 것:**
- `from .execute_unit.auth import AuthUnit` 추가
- `from .execute_unit.system import SystemUnit` 추가
- `from .execute_unit.chat import ChatUnit` 추가
- `from .execute_unit.widget import WidgetUnit` 추가
- `from .execute_unit.user import UserUnit` 추가
- 아래 엔드포인트 함수 본문을 execute_unit 호출로 교체:
  - `send_temp_message` → `ChatUnit.send_temp_message(...)`
  - `flush_sessions` → `SystemUnit.flush_user_sessions(...)`
  - `get_settings` → `SystemUnit.get_settings(...)`
  - `update_settings` → `SystemUnit.update_settings(...)`
  - `get_session_list` → `ChatUnit.get_session_list(...)`
  - `create_session` → `ChatUnit.create_session(...)`
  - `delete_session` → `ChatUnit.delete_session(...)`
  - `leave_session` → `ChatUnit.leave_session(...)`
  - `convert_to_personal` → `ChatUnit.convert_to_personal(...)`
  - `update_session_title` → `ChatUnit.update_session_title(...)`
  - `update_session_color` → `ChatUnit.update_session_color(...)`
  - `get_chat_history` → `ChatUnit.get_chat_history(...)`
  - `send_message` → `ChatUnit.send_message(...)`
  - `send_team_message` → ChatService._handle_team_message 그대로 유지 (하위 호환)
  - `session_events` → `ChatUnit.subscribe_session_events(...)`
  - `invite_user` → `ChatUnit.invite_user(...)`
  - `share_chat` → `ChatUnit.share_chat(...)`
  - `download_chat` → `ChatUnit.download_chat(...)`
  - `upload_files` → `ChatUnit.upload_files(...)`
  - `mark_session_read` → 기존 postgres 직접 호출 유지 (UserUnit 미구현)
  - `send_typing` → `ChatUnit.broadcast_typing(...)`
  - `notification_stream` → `ChatUnit.subscribe_user_notifications(...)`
  - `add_map_marker` → `WidgetUnit.add_marker(request.app.state.map_node, ...)`
  - `delete_map_marker` → `WidgetUnit.delete_marker(request.app.state.map_node, ...)`
  - `save_map_markers` → `WidgetUnit.set_markers(request.app.state.map_node, ...)`
  - `get_map_markers` → `WidgetUnit.get_markers(request.app.state.map_node, ...)`
  - `save_map_routes` → `WidgetUnit.set_routes(request.app.state.map_node, ...)`
  - `get_map_routes` → `WidgetUnit.get_routes(request.app.state.map_node, ...)`
  - `save_trip_range` → `WidgetUnit.set_trip_range(request.app.state.trip_range_node, ...)`
  - `get_trip_range` → `WidgetUnit.get_trip_range(request.app.state.trip_range_node, ...)`
  - auth 엔드포인트 (`signup`, `login`, `refresh`, `logout`, `logout_all_devices`, `get_my_info`) → `AuthUnit.*`

---

# Gemini Evaluation Checklist
1. `memory/cacher.py` 에 Cacher 클래스 존재하고 memo/plan/indicators 메서드 없음?
2. `execute_unit/` 에 5개 파일 (auth.py, system.py, user.py, chat.py, widget.py) 모두 존재?
3. `facade.py` 에서 MemoRequest, PlanRequest 모델 없음?
4. `facade.py` 에서 memo/plan/indicators 엔드포인트 4+1=5개 모두 없음?
5. `loader/loader.py` 에서 memo_node, plan_node import 및 초기화 코드 없음?
6. `flush_service.py` 가 SessionCache 대신 Cacher import?
7. `chat_service.py` 가 SessionCache 대신 Cacher import, memo/plan 메서드 없음?
8. `facade.py` 가 execute_unit 클래스들을 import?
9. spec에 없는 기능 추가 없음?
10. 기존 auth/, system/session_container.py, team_service.py 변경 없음?

# Response Language
Korean
