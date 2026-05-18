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

SESSION_TTL          = 3600 * 8
USER_SESSION_SET_TTL = 3600 * 24
DATA_TTL             = 3600 * 24
USER_DATA_TTL        = 3600 * 8


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
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:current_session",
            "value":  session_id,
            "ttl":    SESSION_TTL,
        })

    @staticmethod
    async def get_current_session(user_id: str, redis) -> Optional[str]:
        result = await redis.execute({
            "action": "get",
            "key":    f"user:{user_id}:current_session",
        })
        return result.get("value")

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
        await redis.execute({"action": "delete", "key": f"session:{session_id}:meta"})

    # ── 마커 / 경로 / 기간 ───────────────────────────────────

    @staticmethod
    async def save_markers(session_id: str, markers: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:markers",
            "value":  json.dumps(markers, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_markers(session_id: str, redis) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:markers"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    @staticmethod
    async def save_routes(session_id: str, marker_ids: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:routes",
            "value":  json.dumps(marker_ids, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_routes(session_id: str, redis) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:routes"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    @staticmethod
    async def save_ranges(session_id: str, ranges: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:ranges",
            "value":  json.dumps(ranges, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_ranges(session_id: str, redis) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:ranges"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    # ── 사용자 프로필 ─────────────────────────────────────────

    @staticmethod
    async def save_user_profile(user_id: str, data: dict, redis) -> None:
        await redis.execute({
            "action":  "hset",
            "key":     f"user:{user_id}:profile",
            "mapping": {k: str(v) for k, v in data.items()},
            "ttl":     USER_DATA_TTL,
        })

    @staticmethod
    async def get_user_profile(user_id: str, redis, manager: Any = None) -> dict:
        result = await redis.execute({"action": "hgetall", "key": f"user:{user_id}:profile"})
        data = result.get("data", {}) or {}
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
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:style",
            "value":  json.dumps(existing, ensure_ascii=False),
            "ttl":    USER_DATA_TTL,
        })

    @staticmethod
    async def get_user_style(user_id: str, redis) -> dict:
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:style"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return {}

    @staticmethod
    async def save_user_travel(user_id: str, data: dict, redis) -> None:
        existing = await Cacher.get_user_travel(user_id, redis)
        existing.update(data)
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:travel",
            "value":  json.dumps(existing, ensure_ascii=False),
            "ttl":    USER_DATA_TTL,
        })

    @staticmethod
    async def get_user_travel(user_id: str, redis) -> dict:
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:travel"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return {}

    @staticmethod
    async def save_ui_settings(user_id: str, data: dict, redis) -> None:
        existing = await Cacher.get_ui_settings(user_id, redis)
        for k, v in data.items():
            if isinstance(existing.get(k), dict) and isinstance(v, dict):
                existing[k].update(v)
            else:
                existing[k] = v
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:ui_settings",
            "value":  json.dumps(existing, ensure_ascii=False),
            "ttl":    USER_DATA_TTL,
        })

    @staticmethod
    async def get_ui_settings(user_id: str, redis) -> dict:
        """UI 설정은 로그인 시 EventHandler가 미리 적재한다. miss시 빈 dict."""
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:ui_settings"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return {}

    # ── 계정 삭제 플래그 ─────────────────────────────────────

    @staticmethod
    async def mark_account_deleted(user_id: str, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:pending_delete",
            "value":  "1",
            "ttl":    USER_DATA_TTL,
        })

    @staticmethod
    async def is_account_deleted(user_id: str, redis) -> bool:
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:pending_delete"})
        return result.get("value") == "1"

    @staticmethod
    async def delete_user_data(user_id: str, redis) -> None:
        for suffix in ("profile", "style", "travel", "ui_settings", "pending_delete"):
            await redis.execute({"action": "delete", "key": f"user:{user_id}:{suffix}"})

    @staticmethod
    async def delete_current_session(user_id: str, redis) -> None:
        await redis.execute({"action": "delete", "key": f"user:{user_id}:current_session"})

    # ── 메모 / 플랜 ──────────────────────────────────────────

    @staticmethod
    async def save_memo(session_id: str, date_key: str, memo: str, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:memo:{date_key}",
            "value":  memo,
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_memo(session_id: str, date_key: str, redis) -> str:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:memo:{date_key}"})
        return result.get("value") or ""

    @staticmethod
    async def save_plan(session_id: str, date_key: str, plan: list, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:plan:{date_key}",
            "value":  json.dumps(plan, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_plan(session_id: str, date_key: str, redis) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:plan:{date_key}"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    @staticmethod
    async def get_indicators(session_id: str, year: int, month: int, redis) -> list:
        dates = set()
        for day in range(1, 32):
            date_key = f"{year}-{month:02d}-{day:02d}"
            memo_r = await redis.execute({"action": "exists", "key": f"session:{session_id}:memo:{date_key}"})
            plan_r = await redis.execute({"action": "exists", "key": f"session:{session_id}:plan:{date_key}"})
            if memo_r.get("exists") or plan_r.get("exists"):
                dates.add(date_key)
        return list(dates)

    # ── 세션 버퍼 (SessionContainer용) ───────────────────────

    @staticmethod
    async def get_personalized_topics(user_id: str, redis) -> str:
        result = await redis.execute({
            "action": "hget", "key": f"user:{user_id}:profile", "field": "personalized_topics",
        })
        return result.get("value") or ""

    @staticmethod
    async def save_session_buf(session_id: str, messages: list, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:buf_msgs",
            "value":  json.dumps(messages, ensure_ascii=False),
            "ttl":    SESSION_TTL,
        })

    @staticmethod
    async def get_session_buf(session_id: str, redis) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:buf_msgs"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    @staticmethod
    async def save_session_msg_count(session_id: str, count: int, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:msg_count",
            "value":  str(count),
            "ttl":    SESSION_TTL,
        })

    @staticmethod
    async def get_session_msg_count(session_id: str, redis) -> int:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:msg_count"})
        try:
            return int(result.get("value") or 0)
        except (ValueError, TypeError):
            return 0

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
        existing = await Cacher.get_messages(session_id, redis)
        existing.append(msg_data)
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:messages",
            "value":  json.dumps(existing, ensure_ascii=False, default=str),
            "ttl":    SESSION_TTL,
        })
        if manager is not None:
            manager.emit(SaveMessageEvent(session_id=session_id, msg_data=msg_data))

    @staticmethod
    async def get_messages(session_id: str, redis, manager: Any = None,
                            limit: int = 40, offset: int = 0) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:messages"})
        val = result.get("value")
        if val:
            try:
                msgs = json.loads(val)
                return msgs[offset:offset + limit] if limit else msgs[offset:]
            except Exception:
                pass
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadMessagesEvent(session_id=session_id, limit=limit, offset=offset, future=fut), priority=True)
        return await fut

    # ── 세션 참여자 ───────────────────────────────────────────

    @staticmethod
    async def save_session_participants(session_id: str, participants: list, redis) -> None:
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:participants",
            "value":  json.dumps(participants, ensure_ascii=False, default=str),
            "ttl":    SESSION_TTL,
        })

    @staticmethod
    async def get_session_participants(session_id: str, redis, manager: Any = None) -> list:
        result = await redis.execute({"action": "get", "key": f"session:{session_id}:participants"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
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
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:notifications",
            "value":  json.dumps(existing, ensure_ascii=False, default=str),
            "ttl":    USER_DATA_TTL,
        })
        if manager is not None:
            manager.emit(SaveNotificationEvent(user_id=user_id, notif_data=notif_data))

    @staticmethod
    async def get_notifications(user_id: str, redis, manager: Any = None, limit: int = 50) -> list:
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:notifications"})
        val = result.get("value")
        if val:
            try:
                msgs = json.loads(val)
                return msgs[-limit:] if limit else msgs
            except Exception:
                pass
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadNotificationsEvent(user_id=user_id, future=fut), priority=True)
        notifs = await fut
        return notifs[-limit:] if notifs else []

    # ── 닉네임 → user_id 역방향 조회 ─────────────────────────

    @staticmethod
    async def get_user_by_nickname(nickname: str, redis, manager: Any = None) -> Optional[str]:
        result = await redis.execute({"action": "get", "key": f"nick:{nickname}:user_id"})
        if result.get("value"):
            return result["value"]
        if manager is None:
            return None
        fut = _future()
        manager.emit(GetUserByNicknameEvent(nickname=nickname, future=fut), priority=True)
        return await fut

    # ── 세션 목록 ─────────────────────────────────────────────

    @staticmethod
    async def get_session_list(user_id: str, trip_id, redis, manager: Any = None) -> list:
        key = f"user:{user_id}:sessions:{trip_id or 'all'}"
        result = await redis.execute({"action": "get", "key": key})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadSessionListEvent(user_id=user_id, trip_id=trip_id, future=fut), priority=True)
        return await fut

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
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:trips"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
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
        await redis.execute({"action": "delete", "key": f"session:{session_id}:participants"})

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
        result = await redis.execute({"action": "get", "key": f"user:{user_id}:teams"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        if manager is None:
            return []
        fut = _future()
        manager.emit(LoadTeamListEvent(user_id=user_id, future=fut), priority=True)
        return await fut

    @staticmethod
    async def get_team_sessions(team_id: str, redis, manager: Any = None) -> list:
        result = await redis.execute({"action": "get", "key": f"team:{team_id}:sessions"})
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
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
