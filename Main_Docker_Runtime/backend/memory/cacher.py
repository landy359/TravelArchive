# [역할] 실행 단위(Execute Unit)와 Redis 사이의 유일한 인터페이스.
#        실행 단위는 PG/Loader를 전혀 모르고, 이 파일의 메서드만 호출한다.
#        Cacher는 절대로 Loader를 직접 호출하지 않는다. cache miss/PG 영속화가 필요하면
#        manager(EventHandler)에 이벤트를 emit해서 위임한다.
#
#        호출 방향: Execute Unit → Cacher → Redis
#                                       ↓ (miss/mutate)
#                                   manager.emit(...) → EventHandler → Loader → PG
#
# Redis Key 구조:
#   user:{user_id}:active_sessions    -> Set
#   user:{user_id}:current_session    -> String
#   session:{session_id}:meta         -> Hash
#   session:{session_id}:markers      -> JSON
#   session:{session_id}:ranges       -> JSON
#   user:{user_id}:profile            -> Hash
#   user:{user_id}:style              -> JSON
#   user:{user_id}:travel             -> JSON
#   user:{user_id}:ui_settings        -> JSON
#   user:{user_id}:pending_delete     -> '1'
import asyncio
import json
from typing import Any, Optional

from .constants import DATA_TTL, SESSION_TTL, USER_ANALYSIS_TTL, USER_DATA_TTL, USER_SESSION_SET_TTL
from .events import (
    AcceptInviteEvent,
    ClearNotifsEvent,
    CreateSessionEvent,
    CreateTeamEvent,
    CreateTripEvent,
    DeleteTripEvent,
    DismissNotifEvent,
    GetMiscTripEvent,
    GetSessionInfoEvent,
    GetSessionRoleEvent,
    GetUserByNicknameEvent,
    InviteUserEvent,
    LeaveAsMasterEvent,
    LeaveSessionEvent,
    LoadMessagesEvent,
    LoadNotificationsEvent,
    LoadSessionListEvent,
    LoadSessionParticipantsEvent,
    LoadTeamListEvent,
    LoadTeamSessionsEvent,
    LoadTripListEvent,
    LoadUserProfileEvent,
    MarkReadEvent,
    MoveSessionTripEvent,
    RemoveNonMasterEvent,
    SaveMessageEvent,
    SaveNotificationEvent,
    SearchUsersEvent,
    UpdateSessionRecordEvent,
    UpdateTripEvent,
)

def _future() -> asyncio.Future:
    return asyncio.get_running_loop().create_future()


class Cacher:

    # ── 활성 세션 Set 관리 ────────────────────────────────────

    @staticmethod
    async def mark_active(user_id: str, session_id: str, redis):
        await redis.execute({
            "action": "sadd",
            "key":    f"user:{user_id}:active_sessions",
            "member": session_id,
        })
        await redis.execute({
            "action": "expire",
            "key":    f"user:{user_id}:active_sessions",
            "ttl":    USER_SESSION_SET_TTL,
        })

    @staticmethod
    async def unmark_active(user_id: str, session_id: str, redis):
        await redis.execute({
            "action": "srem",
            "key":    f"user:{user_id}:active_sessions",
            "member": session_id,
        })

    @staticmethod
    async def get_active_session_ids(user_id: str, redis) -> set:
        result = await redis.execute({
            "action": "smembers",
            "key":    f"user:{user_id}:active_sessions",
        })
        return set(result.get("data", []))

    # ── 현재 세션 추적 ────────────────────────────────────────

    @staticmethod
    async def set_current_session(user_id: str, session_id: str, redis):
        await redis.set_str(f"user:{user_id}:current_session", session_id, SESSION_TTL)

    @staticmethod
    async def get_current_session(user_id: str, redis) -> Optional[str]:
        return await redis.get_str(f"user:{user_id}:current_session")

    # ── 세션 메타 캐시 ───────────────────────────────────────

    @staticmethod
    async def cache_session_meta(session_id: str, meta: dict, redis):
        await redis.execute({
            "action":  "hset",
            "key":     f"session:{session_id}:meta",
            "mapping": {k: str(v) for k, v in meta.items()},
            "ttl":     SESSION_TTL,
        })

    @staticmethod
    async def get_session_meta(session_id: str, redis) -> Optional[dict]:
        result = await redis.execute({
            "action": "hgetall",
            "key":    f"session:{session_id}:meta",
        })
        d = result.get("data", {})
        return d if d else None

    @staticmethod
    async def delete_session_cache(session_id: str, redis):
        await redis.delete(f"session:{session_id}:meta")

    # ── 마커 / 경로 / 기간 ───────────────────────────────────

    @staticmethod
    async def save_markers(session_id: str, markers: list, redis):
        await redis.set_json(f"session:{session_id}:markers", markers, DATA_TTL)

    @staticmethod
    async def get_markers(session_id: str, redis) -> list:
        return await redis.get_json(f"session:{session_id}:markers") or []

    @staticmethod
    async def save_routes(session_id: str, marker_ids: list, redis):
        await redis.set_json(f"session:{session_id}:routes", marker_ids, DATA_TTL)

    @staticmethod
    async def get_routes(session_id: str, redis) -> list:
        return await redis.get_json(f"session:{session_id}:routes") or []

    @staticmethod
    async def save_ranges(session_id: str, ranges: list, redis):
        await redis.set_json(f"session:{session_id}:ranges", ranges, DATA_TTL)

    @staticmethod
    async def get_ranges(session_id: str, redis) -> list:
        return await redis.get_json(f"session:{session_id}:ranges") or []

    # ── 사용자 프로필 ─────────────────────────────────────────

    @staticmethod
    async def save_user_profile(user_id: str, data: dict, redis) -> None:
        await redis.execute({
            "action":  "hset",
            "key":     f"user:{user_id}:profile",
            "mapping": {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v) for k, v in data.items()},
            "ttl":     USER_DATA_TTL,
        })

    @staticmethod
    async def get_user_profile(user_id: str, redis, manager: Any = None) -> dict:
        result = await redis.execute({"action": "hgetall", "key": f"user:{user_id}:profile"})
        data = result.get("data", {}) or {}
        if "extra_contacts" in data and isinstance(data["extra_contacts"], str):
            try:
                data["extra_contacts"] = json.loads(data["extra_contacts"])
            except Exception:
                data["extra_contacts"] = []
        if data or manager is None:
            return data
        fut = _future()
        manager.emit(LoadUserProfileEvent(user_id=user_id, future=fut), priority=True)
        return await fut

    # ── 사용자 스타일 / 여행 취향 / UI 설정 ──────────────────

    @staticmethod
    async def save_user_style(user_id: str, data: dict, redis) -> None:
        existing = await Cacher.get_user_style(user_id, redis)
        existing.update(data)
        await redis.set_json(f"user:{user_id}:style", existing, USER_DATA_TTL)

    @staticmethod
    async def get_user_style(user_id: str, redis) -> dict:
        return await redis.get_json(f"user:{user_id}:style") or {}

    @staticmethod
    async def save_user_travel(user_id: str, data: dict, redis) -> None:
        existing = await Cacher.get_user_travel(user_id, redis)
        existing.update(data)
        await redis.set_json(f"user:{user_id}:travel", existing, USER_DATA_TTL)

    @staticmethod
    async def get_user_travel(user_id: str, redis) -> dict:
        return await redis.get_json(f"user:{user_id}:travel") or {}

    @staticmethod
    async def save_ui_settings(user_id: str, data: dict, redis) -> None:
        existing = await Cacher.get_ui_settings(user_id, redis)
        for k, v in data.items():
            if isinstance(existing.get(k), dict) and isinstance(v, dict):
                existing[k].update(v)
            else:
                existing[k] = v
        await redis.set_json(f"user:{user_id}:ui_settings", existing, USER_DATA_TTL)

    @staticmethod
    async def get_ui_settings(user_id: str, redis) -> dict:
        """UI 설정은 로그인 시 EventHandler가 미리 적재한다. miss시 빈 dict."""
        return await redis.get_json(f"user:{user_id}:ui_settings") or {}

    # ── 계정 삭제 플래그 ─────────────────────────────────────

    @staticmethod
    async def mark_account_deleted(user_id: str, redis) -> None:
        await redis.set_str(f"user:{user_id}:pending_delete", "1", USER_DATA_TTL)

    @staticmethod
    async def is_account_deleted(user_id: str, redis) -> bool:
        return await redis.get_str(f"user:{user_id}:pending_delete") == "1"

    @staticmethod
    async def delete_user_data(user_id: str, redis) -> None:
        for suffix in ("profile", "style", "travel", "ui_settings", "pending_delete", "analysis", "sessions:all"):
            await redis.delete(f"user:{user_id}:{suffix}")

    @staticmethod
    async def delete_current_session(user_id: str, redis) -> None:
        await redis.delete(f"user:{user_id}:current_session")

    # ── 메모 / 플랜 ──────────────────────────────────────────

    @staticmethod
    async def save_memo(session_id: str, date_key: str, memo: str, redis) -> None:
        await redis.set_str(f"session:{session_id}:memo:{date_key}", memo, DATA_TTL)

    @staticmethod
    async def get_memo(session_id: str, date_key: str, redis) -> str:
        return await redis.get_str(f"session:{session_id}:memo:{date_key}") or ""

    @staticmethod
    async def save_plan(session_id: str, date_key: str, plan: list, redis) -> None:
        await redis.set_json(f"session:{session_id}:plan:{date_key}", plan, DATA_TTL)

    @staticmethod
    async def get_plan(session_id: str, date_key: str, redis) -> list:
        return await redis.get_json(f"session:{session_id}:plan:{date_key}") or []

    @staticmethod
    async def get_indicators(session_id: str, year: int, month: int, redis) -> list:
        day_keys = [f"{year}-{month:02d}-{day:02d}" for day in range(1, 32)]
        all_keys = [
            k
            for date_key in day_keys
            for k in (
                f"session:{session_id}:memo:{date_key}",
                f"session:{session_id}:plan:{date_key}",
            )
        ]
        found = await redis.exists_many(all_keys)
        dates = {
            date_key
            for date_key in day_keys
            if f"session:{session_id}:memo:{date_key}" in found
            or f"session:{session_id}:plan:{date_key}" in found
        }
        return list(dates)

    # ── 세션 버퍼 (SessionContainer용) ───────────────────────

    @staticmethod
    async def get_personalized_topics(user_id: str, redis) -> str:
        result = await redis.execute({
            "action": "hget", "key": f"user:{user_id}:profile", "field": "personalized_topics",
        })
        return result.get("value") or ""

    @staticmethod
    async def get_user_analysis(user_id: str, redis) -> str:
        return await redis.get_str(f"user:{user_id}:analysis") or ""

    @staticmethod
    async def save_user_analysis(user_id: str, analysis: str, redis) -> None:
        await redis.set_str(f"user:{user_id}:analysis", analysis, USER_ANALYSIS_TTL)
        # profile hash의 personalized_topics 동기화 (GENERATION_PROMPT 경로)
        await redis.execute({
            "action": "hset", "key": f"user:{user_id}:profile",
            "mapping": {"personalized_topics": analysis},
            "ttl": USER_DATA_TTL,
        })

    @staticmethod
    async def save_session_buf(session_id: str, messages: list, redis) -> None:
        await redis.set_json(f"session:{session_id}:buf_msgs", messages, SESSION_TTL)

    @staticmethod
    async def get_session_buf(session_id: str, redis) -> list:
        return await redis.get_json(f"session:{session_id}:buf_msgs") or []

    @staticmethod
    async def save_session_msg_count(session_id: str, count: int, redis) -> None:
        await redis.set_str(f"session:{session_id}:msg_count", str(count), SESSION_TTL)

    @staticmethod
    async def get_session_msg_count(session_id: str, redis) -> int:
        value = await redis.get_str(f"session:{session_id}:msg_count")
        try:
            return int(value or 0)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    async def save_session_widgets(session_id: str, data: dict, redis) -> None:
        await redis.set_json(f"session:{session_id}:widgets", data, SESSION_TTL)

    @staticmethod
    async def get_session_widgets(session_id: str, redis) -> dict:
        return await redis.get_json(f"session:{session_id}:widgets") or {}

    @staticmethod
    async def mark_dirty_widget(session_id: str, widget_type: str, redis) -> None:
        await redis.execute({
            "action": "sadd",
            "key":    f"session:{session_id}:dirty_widgets",
            "member": widget_type,
        })

    # ── 메시지 (Redis = SoT, PG 영속화는 이벤트) ──────────────

    @staticmethod
    async def save_message(session_id: str, msg_data: dict, redis, manager: Any = None) -> None:
        await redis.rpush_json(f"session:{session_id}:messages", msg_data, SESSION_TTL)
        if manager is not None:
            manager.emit(SaveMessageEvent(session_id=session_id, msg_data=msg_data))

    @staticmethod
    async def get_messages(session_id: str, redis, manager: Any = None,
                            limit: int = 40, offset: int = 0) -> list:
        key = f"session:{session_id}:messages"
        if await redis.exists(key):
            end = offset + limit - 1 if limit else -1
            return await redis.lrange_json(key, offset, end)
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadMessagesEvent(session_id=session_id, limit=limit, offset=offset, future=fut), priority=True)
        return await fut

    # ── 세션 참여자 ───────────────────────────────────────────

    @staticmethod
    async def save_session_participants(session_id: str, participants: list, redis) -> None:
        await redis.set_json(f"session:{session_id}:participants", participants, SESSION_TTL)

    @staticmethod
    async def get_session_participants(session_id: str, redis, manager: Any = None) -> list:
        cached = await redis.get_json(f"session:{session_id}:participants")
        if cached is not None:
            return cached
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadSessionParticipantsEvent(session_id=session_id, future=fut), priority=True)
        return await fut

    # ── 알림 ─────────────────────────────────────────────────

    @staticmethod
    async def save_notification(user_id: str, notif_data: dict, redis, manager: Any = None) -> None:
        existing = await Cacher.get_notifications(user_id, redis)
        existing.append(notif_data)
        await redis.set_json(f"user:{user_id}:notifications", existing, USER_DATA_TTL)
        if manager is not None:
            manager.emit(SaveNotificationEvent(user_id=user_id, notif_data=notif_data))

    @staticmethod
    async def get_notifications(user_id: str, redis, manager: Any = None, limit: int = 50) -> list:
        cached = await redis.get_json(f"user:{user_id}:notifications")
        if cached is not None:
            return cached[-limit:] if limit else cached
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadNotificationsEvent(user_id=user_id, future=fut), priority=True)
        notifs = await fut
        return notifs[-limit:] if notifs else []

    # ── 닉네임 → user_id 역방향 조회 ─────────────────────────

    @staticmethod
    async def get_user_by_nickname(nickname: str, redis, manager: Any = None) -> Optional[str]:
        cached = await redis.get_str(f"nick:{nickname}:user_id")
        if cached:
            return cached
        if manager is None:
            return None
        fut = _future()
        manager.emit(GetUserByNicknameEvent(nickname=nickname, future=fut), priority=True)
        return await fut

    # ── 세션 목록 (Redis = source of truth) ────────────────────
    #   user:{user_id}:sessions:all → 전체 세션 JSON 배열 (Redis-authoritative)
    #   trip 필터링은 Redis에서 in-memory 필터링으로 처리
    #   로그인 시 PG → Redis 1회 로드, 이후 모든 mutation은 Redis 우선

    @staticmethod
    async def get_session_list(user_id: str, trip_id, redis, manager: Any = None) -> list:
        """Redis-only 읽기. cache miss 시 PG에서 1회 로드 (로그인 직후/만료 후 fallback)."""
        all_key = f"user:{user_id}:sessions:all"
        sessions: list = await redis.get_json(all_key) or []
        if not sessions:
            if manager is None:
                return []
            fut = _future()
            manager.emit(LoadSessionListEvent(user_id=user_id, trip_id=None, future=fut), priority=True)
            sessions = await fut or []

        if not trip_id or trip_id == "all":
            return sessions
        if trip_id == "misc":
            return [s for s in sessions if s.get("trip_is_misc")]
        return [s for s in sessions if s.get("trip_id") == trip_id]

    @staticmethod
    async def session_list_remove(user_id: str, session_id: str, redis) -> None:
        """Redis 세션 목록에서 1건 제거 (즉시 반영)."""
        key = f"user:{user_id}:sessions:all"
        sessions = await redis.get_json(key)
        if sessions is None:
            return
        sessions = [s for s in sessions if s.get("session_id") != session_id]
        await redis.set_json(key, sessions, SESSION_TTL)

    @staticmethod
    async def session_list_add(user_id: str, session_data: dict, redis) -> None:
        """Redis 세션 목록 맨 앞에 추가 (이미 있으면 교체)."""
        key = f"user:{user_id}:sessions:all"
        sessions = await redis.get_json(key) or []
        sid = session_data.get("session_id")
        sessions = [s for s in sessions if s.get("session_id") != sid]
        sessions.insert(0, session_data)
        await redis.set_json(key, sessions, SESSION_TTL)

    @staticmethod
    async def session_list_update(user_id: str, session_id: str, updates: dict, redis) -> None:
        """Redis 세션 목록의 특정 항목 필드 갱신 (title/color/trip 등)."""
        key = f"user:{user_id}:sessions:all"
        sessions = await redis.get_json(key)
        if sessions is None:
            return
        for s in sessions:
            if s.get("session_id") == session_id:
                s.update(updates)
                break
        await redis.set_json(key, sessions, SESSION_TTL)

    # ── 세션/여행/팀 mutation — 모두 manager 경유 ──────────────

    @staticmethod
    async def ensure_misc_trip(user_id: str, redis, manager: Any) -> str:
        fut = _future()
        manager.emit(GetMiscTripEvent(user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def create_session(session_id: str, user_id: str, data: dict, redis, manager: Any) -> None:
        fut = _future()
        manager.emit(CreateSessionEvent(session_id=session_id, user_id=user_id, data=data, future=fut), priority=True)
        await fut

    @staticmethod
    async def get_trip_list(user_id: str, redis, manager: Any = None) -> list:
        cached = await redis.get_json(f"user:{user_id}:trips")
        if cached is not None:
            return cached
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadTripListEvent(user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def create_trip(user_id: str, data: dict, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(CreateTripEvent(user_id=user_id, data=data, future=fut), priority=True)
        return await fut

    @staticmethod
    async def update_trip(trip_id: str, user_id: str, data: dict, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(UpdateTripEvent(trip_id=trip_id, user_id=user_id, data=data, future=fut), priority=True)
        return await fut

    @staticmethod
    async def delete_trip(trip_id: str, user_id: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(DeleteTripEvent(trip_id=trip_id, user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def leave_session(session_id: str, user_id: str, redis, manager: Any) -> None:
        await Cacher.unmark_active(user_id, session_id, redis)
        manager.emit(LeaveSessionEvent(session_id=session_id, user_id=user_id))

    @staticmethod
    async def leave_as_master(session_id: str, user_id: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(LeaveAsMasterEvent(session_id=session_id, user_id=user_id, future=fut), priority=True)
        result = await fut
        await Cacher.unmark_active(user_id, session_id, redis)
        return result

    @staticmethod
    async def get_session_role(session_id: str, user_id: str, redis, manager: Any) -> Optional[str]:
        fut = _future()
        manager.emit(GetSessionRoleEvent(session_id=session_id, user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def remove_non_master_participants(session_id: str, redis, manager: Any) -> None:
        manager.emit(RemoveNonMasterEvent(session_id=session_id))
        await redis.delete(f"session:{session_id}:participants")

    @staticmethod
    async def update_session_record(session_id: str, data: dict, redis, manager: Any) -> None:
        manager.emit(UpdateSessionRecordEvent(session_id=session_id, data=data))

    @staticmethod
    async def invite_to_session(session_id: str, inviter_id: str, invitee: str,
                                 redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(InviteUserEvent(session_id=session_id, inviter_id=inviter_id,
                                      invitee=invitee, future=fut), priority=True)
        return await fut

    @staticmethod
    async def move_session_to_trip(session_id: str, trip_id: Optional[str], user_id: str,
                                    redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(MoveSessionTripEvent(session_id=session_id, trip_id=trip_id,
                                           user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def mark_session_read(session_id: str, user_id: str, redis, manager: Any) -> None:
        manager.emit(MarkReadEvent(session_id=session_id, user_id=user_id))

    @staticmethod
    async def get_session_info(session_id: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(GetSessionInfoEvent(session_id=session_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def search_users(q: str, user_id: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(SearchUsersEvent(q=q, user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def accept_session_invite(notification_id: str, user_id: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(AcceptInviteEvent(notification_id=notification_id, user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def dismiss_notification(notification_id: str, user_id: str, redis, manager: Any) -> None:
        manager.emit(DismissNotifEvent(notification_id=notification_id, user_id=user_id))

    @staticmethod
    async def clear_viewed_notifications(user_id: str, redis, manager: Any) -> None:
        manager.emit(ClearNotifsEvent(user_id=user_id))

    # ── 팀 ────────────────────────────────────────────────────

    @staticmethod
    async def create_team(user_id: str, name: str, redis, manager: Any) -> dict:
        fut = _future()
        manager.emit(CreateTeamEvent(user_id=user_id, name=name, future=fut), priority=True)
        return await fut

    @staticmethod
    async def get_user_teams(user_id: str, redis, manager: Any = None) -> list:
        cached = await redis.get_json(f"user:{user_id}:teams")
        if cached is not None:
            return cached
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadTeamListEvent(user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def get_team_sessions(team_id: str, redis, manager: Any = None) -> list:
        cached = await redis.get_json(f"team:{team_id}:sessions")
        if cached is not None:
            return cached
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadTeamSessionsEvent(team_id=team_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def check_session_participant(session_id: str, user_id: str, redis, manager: Any = None) -> bool:
        participants = await Cacher.get_session_participants(session_id, redis, manager)
        return any(p.get("user_id") == user_id for p in participants)

    @staticmethod
    async def check_pending_invite(session_id: str, invitee_id: str, redis) -> bool:
        notifs = await Cacher.get_notifications(invitee_id, redis)
        return any(
            n.get("type") == "session_invite"
            and n.get("reference_id") == session_id
            and not n.get("is_read")
            for n in notifs
        )
