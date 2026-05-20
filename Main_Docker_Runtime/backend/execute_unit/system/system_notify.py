"""notify_service.py  [domain / system 카테고리]

역할:
  SSE(Server-Sent Events) 채널 관리와 알림 push 전담.
  - 팀 세션 이벤트 SSE: 메시지·타이틀변경·kicked·new_master 브로드캐스트
  - 사용자별 알림 SSE: 세션초대·멘션·new_message 실시간 push

호출 방향:
  SystemUnit → NotifyService
  ChatService → NotifyService (SSE 브로드캐스트)
  TeamService → NotifyService (초대 알림 push)
"""
import asyncio
import json
from typing import Dict, List, Optional, Set

from fastapi.responses import StreamingResponse

# ── 팀 채팅 SSE 구독 큐 ─────────────────────────────────────
# session_id → [asyncio.Queue, ...]
_session_sse_queues: Dict[str, List[asyncio.Queue]] = {}
# queue id → user_id  (자기 자신 메시지 제외용)
_queue_to_user: Dict[int, str] = {}

# ── 사용자별 알림 SSE 큐 ──────────────────────────────────────
# user_id → [asyncio.Queue, ...]
_user_notif_queues: Dict[str, List[asyncio.Queue]] = {}


class NotifyService:

    # ── 세션 SSE 브로드캐스트 ────────────────────────────────

    @staticmethod
    def push_to_session(session_id: str, event_data: str,
                        exclude_user: Optional[str] = None) -> None:
        """세션 SSE 구독자 전원에게 이벤트 push. exclude_user는 제외."""
        for q in list(_session_sse_queues.get(session_id, [])):
            if exclude_user and _queue_to_user.get(id(q)) == exclude_user:
                continue
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                pass

    @staticmethod
    def get_session_viewers(session_id: str) -> Set[str]:
        """현재 세션 SSE를 구독 중인 user_id 집합."""
        return {
            uid for q in _session_sse_queues.get(session_id, [])
            if (uid := _queue_to_user.get(id(q))) is not None
        }

    @staticmethod
    async def subscribe_session_events(session_id: str, user_id: str) -> StreamingResponse:
        """팀 세션 실시간 이벤트 스트림 (Server-Sent Events)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        _session_sse_queues.setdefault(session_id, []).append(q)
        _queue_to_user[id(q)] = user_id

        async def _gen():
            try:
                yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {data}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    _session_sse_queues.get(session_id, []).remove(q)
                except (ValueError, AttributeError):
                    pass
                _queue_to_user.pop(id(q), None)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 사용자 알림 SSE ──────────────────────────────────────

    @staticmethod
    async def subscribe_user_notifications(user_id: str) -> StreamingResponse:
        """사용자 전용 알림 실시간 스트림."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        _user_notif_queues.setdefault(user_id, []).append(q)

        async def _gen():
            try:
                yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"
                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {data}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    _user_notif_queues.get(user_id, []).remove(q)
                except (ValueError, AttributeError):
                    pass

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @staticmethod
    def push_to_user(user_id: str, notif_data: dict) -> None:
        """초대·멘션 등 이벤트 발생 시 해당 사용자 알림 큐에 push."""
        event_data = json.dumps({"type": "notification", **notif_data}, ensure_ascii=False)
        for q in list(_user_notif_queues.get(user_id, [])):
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                pass

    @staticmethod
    async def get_user_notifications(user_id: str, redis, manager) -> list:
        from ...memory.cacher import Cacher
        return await Cacher.get_notifications(user_id, redis, manager)

    @staticmethod
    async def accept_session_invite(redis, manager, notification_id: str, user_id: str) -> dict:
        from ...memory.cacher import Cacher
        return await Cacher.accept_session_invite(notification_id, user_id, redis, manager)

    @staticmethod
    async def dismiss_notification(redis, manager, notification_id: str, user_id: str) -> None:
        from ...memory.cacher import Cacher
        await Cacher.dismiss_notification(notification_id, user_id, redis, manager)

    @staticmethod
    async def clear_viewed_notifications(redis, manager, user_id: str) -> None:
        from ...memory.cacher import Cacher
        await Cacher.clear_viewed_notifications(user_id, redis, manager)

    @staticmethod
    def get_active_session_info() -> list:
        return [
            {"session_id": sid, "sse_subscribers": len(qs)}
            for sid, qs in _session_sse_queues.items()
            if qs
        ]
