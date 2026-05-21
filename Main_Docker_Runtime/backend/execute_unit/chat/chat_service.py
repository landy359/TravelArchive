"""chat_service.py  [domain / chat 카테고리]

역할:
  대화와 관련된 인프라 전반 — 세션 생명주기·메시지 전송·파일·기록·공유.
  PG 접근은 Cacher → manager(EventHandler) 경로만 사용한다.
"""

import asyncio
import json
import os
import re as _re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from ...memory.cacher import Cacher
from ..system.system_notify import NotifyService
from .chat_flush_service import FlushService
from .chat_session_container import SessionContainer

# 임시 세션 저장소 — (container, last_access_ts) 쌍으로 보관
_temp_sessions: Dict[str, tuple[SessionContainer, float]] = {}
_TEMP_SESSION_TTL = 3600  # 1시간 미사용 시 제거
_BACKGROUND_TASKS: set[asyncio.Task] = set()  # create_task GC 방지


def _evict_temp_sessions() -> None:
    now = time.monotonic()
    expired = [k for k, (_, ts) in _temp_sessions.items() if now - ts > _TEMP_SESSION_TTL]
    for k in expired:
        _temp_sessions.pop(k, None)


def _spawn_task(coro) -> asyncio.Task:
    """create_task + GC 방지 참조 관리."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


class ChatService:

    @staticmethod
    async def send_temp_message(temp_session_id: str, message: str) -> StreamingResponse:
        """비로그인 임시채팅 전용. DB/Redis 저장 없음."""
        _evict_temp_sessions()
        now_ts = time.monotonic()
        if temp_session_id not in _temp_sessions:
            _temp_sessions[temp_session_id] = (SessionContainer(session_id=temp_session_id, user_id="TEMP"), now_ts)
        container, _ = _temp_sessions[temp_session_id]
        _temp_sessions[temp_session_id] = (container, now_ts)  # 접근 시마다 TTL 갱신

        async def _stream():
            response_text = await container.process_user_input(message)
            for char in response_text:
                yield char
                await asyncio.sleep(0.03)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def get_session_list(trip_id: Optional[str], user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        sessions = await Cacher.get_session_list(user_id, trip_id, redis, manager)
        return {"sessions": sessions}

    @staticmethod
    async def create_session(user_id: str, trip_id: Optional[str], redis: Any, manager: Any) -> dict[str, Any]:
        session_id = "session_" + str(uuid.uuid4())[:8]
        title = "새 세션"
        if not trip_id:
            trip_id = await Cacher.ensure_misc_trip(user_id, redis, manager)

        trip_color = None
        trip_title = None
        trip_is_misc = False
        for trip in await Cacher.get_trip_list(user_id, redis, manager):
            if trip.get("trip_id") == trip_id:
                trip_color = trip.get("color")
                trip_title = trip.get("title")
                trip_is_misc = trip.get("is_misc", False)
                break

        now = datetime.now(tz=timezone.utc).isoformat()
        list_entry = {
            "session_id": session_id,
            "title": title,
            "topic": "",
            "color": None,
            "trip_id": trip_id,
            "is_manual_title": False,
            "created_at": now,
            "updated_at": now,
            "trip_color": trip_color,
            "trip_title": trip_title,
            "trip_is_misc": trip_is_misc,
            "user_role": "master",
            "participant_count": 1,
            "unread_count": 0,
        }
        # Redis-first: 사용자 세션 목록에 즉시 추가
        await Cacher.session_list_add(user_id, list_entry, redis)
        # PG 영속화는 fire-and-forget으로 만들기 위해 emit (await는 유지: session_participants 정합성 필요)
        await Cacher.create_session(session_id, user_id, {"title": title, "trip_id": trip_id}, redis, manager)

        return {
            "id": session_id,
            "title": title,
            "trip_id": trip_id,
            "trip_color": trip_color,
            "user_id": user_id,
            "created_at": date.today().isoformat(),
            "participant_count": 1,
            "user_role": "master",
        }

    @staticmethod
    async def leave_session(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, bool]:
        # Redis-first: 사용자 세션 목록에서 즉시 제거
        await Cacher.session_list_remove(user_id, session_id, redis)
        # PG sync (fire-and-forget within event handler)
        await Cacher.leave_session(session_id, user_id, redis, manager)
        NotifyService.push_to_user(user_id, {
            "type": "session_left",
            "session_id": session_id,
        })
        return {"success": True}

    @staticmethod
    async def delete_session(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from fastapi import HTTPException
        # Redis-first: 즉시 사용자 목록에서 제거 → 클라이언트가 새 목록 받으면 사라진 상태
        await Cacher.session_list_remove(user_id, session_id, redis)
        try:
            result = await Cacher.leave_as_master(session_id, user_id, redis, manager)
        except HTTPException as e:
            if e.status_code in (404, 403):
                return {"success": True, "deleted": True}
            raise
        if result["deleted"]:
            NotifyService.push_to_session(session_id, json.dumps({
                "type": "kicked",
                "session_id": session_id,
                "reason": "session_deleted",
            }, ensure_ascii=False))
            await FlushService.flush_single_session(session_id, redis, manager)
        else:
            new_master_uid = result.get("new_master")
            if new_master_uid:
                # 새 마스터의 Redis 세션 목록에서 user_role 갱신 + 참여자 수 -1
                await Cacher.session_list_update(
                    new_master_uid, session_id,
                    {"user_role": "master"},
                    redis,
                )
            NotifyService.push_to_session(session_id, json.dumps({
                "type": "new_master",
                "session_id": session_id,
                "user_id": new_master_uid,
            }, ensure_ascii=False))
        return {"success": True, "deleted": result["deleted"]}

    @staticmethod
    async def convert_to_personal(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, bool]:
        from fastapi import HTTPException

        role = await Cacher.get_session_role(session_id, user_id, redis, manager)
        if role != "master":
            raise HTTPException(status_code=403, detail="마스터만 개인 전환을 할 수 있습니다")

        # kicked될 멤버 목록 미리 확보 → 각자의 Redis 세션 목록에서 제거 (Redis-first)
        participants = await Cacher.get_session_participants(session_id, redis, manager)
        kicked_uids = [p["user_id"] for p in participants
                       if p.get("user_id") not in (user_id, "bot") and p.get("role") != "master"]
        for uid in kicked_uids:
            await Cacher.session_list_remove(uid, session_id, redis)
        # 마스터의 list_entry는 participant_count = 1로 갱신
        await Cacher.session_list_update(user_id, session_id, {"participant_count": 1}, redis)

        NotifyService.push_to_session(session_id, json.dumps({
            "type": "kicked",
            "session_id": session_id,
            "reason": "master_converted_to_personal",
        }, ensure_ascii=False), exclude_user=user_id)
        await Cacher.remove_non_master_participants(session_id, redis, manager)
        return {"success": True}

    @staticmethod
    async def update_session_title(session_id: str, title: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        meta = await Cacher.get_session_meta(session_id, redis) or {}
        meta["name"] = title
        meta["is_manual_title"] = "true"
        await Cacher.cache_session_meta(session_id, meta, redis)
        # Redis 세션 목록: 모든 참여자 항목 갱신 (팀 세션이면 다른 멤버도)
        await ChatService._sync_title_to_redis_list(session_id, title, redis, manager)
        await Cacher.session_list_update(user_id, session_id, {"is_manual_title": True}, redis)
        await Cacher.update_session_record(session_id, {"title": title, "is_manual_title": True}, redis, manager)
        NotifyService.push_to_session(session_id, json.dumps({
            "type": "title_updated",
            "session_id": session_id,
            "title": title,
        }, ensure_ascii=False))
        return {"success": True, "title": title}

    @staticmethod
    async def update_session_color(session_id: str, color: str, user_id: str, redis: Any, manager: Any) -> dict[str, str]:
        participants = await Cacher.get_session_participants(session_id, redis, manager)
        for p in participants:
            uid = p.get("user_id")
            if uid and uid != "bot":
                await Cacher.session_list_update(uid, session_id, {"color": color}, redis)
        await Cacher.update_session_record(session_id, {"color": color}, redis, manager)
        NotifyService.push_to_session(session_id, json.dumps({
            "type": "color_updated",
            "session_id": session_id,
            "color": color,
        }, ensure_ascii=False), exclude_user=user_id)
        return {"success": True, "color": color}

    @staticmethod
    async def invite_user(session_id: str, invitee: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        result = await Cacher.invite_to_session(session_id, user_id, invitee, redis, manager)
        NotifyService.push_to_user(invitee, {
            "notification_id": result.get("notification_id"),
            "sub_type": "session_invite",
            "message": result.get("message"),
            "session_id": session_id,
        })
        return {"success": True, "session_id": session_id, "invitee": invitee, "notification_id": result.get("notification_id")}

    @staticmethod
    async def share_chat(session_id: str, user_id: str) -> dict[str, str | bool]:
        return {"success": True, "share_url": f"/share/{session_id}"}

    @staticmethod
    async def _get_container(session_id: str, user_id: str, redis: Any) -> SessionContainer:
        """항상 새 컨테이너를 생성하고 Redis에서 상태를 복원."""
        container = SessionContainer(session_id=session_id, user_id=user_id)
        await container.load_from_redis(redis)
        return container

    @staticmethod
    async def send_message(session_id: str, message: str, user_id: str, redis: Any, manager: Any) -> StreamingResponse:
        return await ChatService._handle_session_message(session_id, user_id, message, redis, manager)

    @staticmethod
    async def _handle_session_message(session_id: str, user_id: str, message: str, redis: Any, manager: Any) -> StreamingResponse:
        """모든 세션: 메시지 저장 + SessionContainer 주제추론. 팀은 SSE 브로드캐스트."""
        now = datetime.now(tz=timezone.utc)
        msg_id = "msg_" + str(uuid.uuid4())[:12]

        profile = await Cacher.get_user_profile(user_id, redis, manager)
        sender_name = (profile.get("nickname") or "").strip() or "사용자"

        await Cacher.save_message(session_id, {
            "message_id": msg_id,
            "session_id": session_id,
            "sender_id": user_id,
            "sender_name": sender_name,
            "sender_type": "user",
            "message_type": "text",
            "content": message,
            "created_at": now.isoformat(),
        }, redis, manager)

        participants = await Cacher.get_session_participants(session_id, redis, manager)
        other_ids = [p["user_id"] for p in participants if p.get("user_id") != user_id and p.get("user_id") != "bot"]
        is_team = len(other_ids) > 0

        await ChatService._notify_mentions(session_id, user_id, sender_name, message, now, redis, manager)
        if is_team:
            ChatService._broadcast_user_message(session_id, user_id, sender_name, message, msg_id, now)
            ChatService._push_unviewed_user_notices(session_id, other_ids, sender_name, message)

        if not is_team:
            bot_query = _re.sub(r'^@BOT\s+', '', message, flags=_re.IGNORECASE).strip()
            return await ChatService._stream_bot_response(session_id, bot_query, user_id, redis, manager)

        bot_match = _re.match(r'^@BOT\s+([\s\S]+)', message, _re.IGNORECASE)
        if bot_match:
            return await ChatService._stream_bot_response(session_id, bot_match.group(1).strip(), user_id, redis, manager)

        _spawn_task(ChatService._run_ingest(session_id, user_id, message, redis, manager))

        async def _ack():
            yield b''

        return StreamingResponse(_ack(), media_type="text/plain")

    @staticmethod
    async def _notify_mentions(session_id: str, user_id: str, sender_name: str, message: str, now: datetime, redis: Any, manager: Any) -> None:
        for mention_nick in set(_re.findall(r'@(\S+)', message)):
            target_uid = await Cacher.get_user_by_nickname(mention_nick, redis, manager)
            if target_uid and target_uid != user_id:
                notif_data = {
                    "notification_id": "notif_" + str(uuid.uuid4())[:12],
                    "user_id": target_uid,
                    "type": "mention",
                    "reference_type": "session",
                    "reference_id": session_id,
                    "message": f"{sender_name}님이 '@{mention_nick}'님을 언급했습니다",
                    "is_read": False,
                    "created_at": now.isoformat(),
                }
                await Cacher.save_notification(target_uid, notif_data, redis, manager)
                NotifyService.push_to_user(target_uid, {
                    "sub_type": "mention",
                    "message": notif_data["message"],
                    "session_id": session_id,
                })

    @staticmethod
    def _broadcast_user_message(session_id: str, user_id: str, sender_name: str, message: str, msg_id: str, now: datetime) -> None:
        NotifyService.push_to_session(session_id, json.dumps({
            "type": "message",
            "sender_id": user_id,
            "sender_name": sender_name,
            "content": message,
            "msg_id": msg_id,
            "ts": now.isoformat(),
        }, ensure_ascii=False))

    @staticmethod
    def _push_unviewed_user_notices(session_id: str, other_ids: list[str], sender_name: str, message: str) -> None:
        viewing_user_ids = NotifyService.get_session_viewers(session_id)
        for other_uid in other_ids:
            if other_uid not in viewing_user_ids:
                NotifyService.push_to_user(other_uid, {
                    "sub_type": "new_message",
                    "message": f"{sender_name}: {message[:50]}",
                    "session_id": session_id,
                })

    @staticmethod
    async def _run_ingest(session_id: str, user_id: str, message: str, redis: Any, manager: Any) -> None:
        try:
            container = await ChatService._get_container(session_id, user_id, redis)
            await container.commit_turn(user_text=message)
            await ChatService._apply_title_change(container, session_id, user_id, redis, manager)
        except Exception as e:
            print(f"[ChatService._run_ingest] {session_id} 오류: {e}")

    @staticmethod
    async def _sync_title_to_redis_list(session_id: str, new_title: str, redis: Any, manager: Any) -> None:
        try:
            participants = await Cacher.get_session_participants(session_id, redis, manager)
            for p in participants:
                uid = p.get("user_id")
                if uid and uid != "bot":
                    await Cacher.session_list_update(uid, session_id, {"title": new_title}, redis)
        except Exception as e:
            print(f"[ChatService._sync_title_to_redis_list] {session_id} 오류: {e}")

    @staticmethod
    async def _apply_title_change(container: Any, session_id: str, user_id: str, redis: Any, manager: Any) -> None:
        if not container.last_topic_change:
            return
        from ...memory.events import UpdateSessionRecordEvent
        from ..user.user_analyze import UserAnalyze
        await ChatService._sync_title_to_redis_list(session_id, container.session_name, redis, manager)
        NotifyService.push_to_session(session_id, json.dumps({
            "type": "title_updated",
            "session_id": session_id,
            "title": container.session_name,
        }, ensure_ascii=False))
        manager.emit(UpdateSessionRecordEvent(
            session_id=session_id,
            data={"title": container.session_name, "topic": container.session_topic},
        ))
        prev = container.last_topic_change["prev"]
        new = container.last_topic_change["new"]
        container.last_topic_change = None
        _spawn_task(UserAnalyze.run_on_topic_change(
            user_id=user_id,
            session_id=session_id,
            prev_topic=prev,
            new_topic=new,
            redis=redis,
            manager=manager,
        ))

    @staticmethod
    async def _stream_bot_response(session_id: str, query: str, triggering_user_id: str, redis: Any, manager: Any) -> StreamingResponse:

        async def _stream():
            bot_text = "죄송합니다, 응답을 생성할 수 없습니다."
            try:
                container = await ChatService._get_container(session_id, triggering_user_id, redis)
                from ...router.core import Core
                bot_text, new_widgets = await Core.run(current=query, **container.router_context())
                await container.commit_turn(user_text=query, bot_text=bot_text, widget_state=new_widgets)
                await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
            except Exception as e:
                print(f"[ChatService._stream_bot_response] {session_id} 오류: {e}")

            bot_now = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id": bot_msg_id,
                "session_id": session_id,
                "sender_id": None,
                "sender_name": "AI",
                "sender_type": "ai",
                "message_type": "text",
                "content": bot_text,
                "created_at": bot_now.isoformat(),
            }, redis, manager)

            NotifyService.push_to_session(session_id, json.dumps({
                "type": "message",
                "sender_id": "bot",
                "sender_name": "AI",
                "content": bot_text,
                "msg_id": bot_msg_id,
                "ts": bot_now.isoformat(),
            }, ensure_ascii=False), exclude_user=triggering_user_id)

            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def get_chat_history(session_id: str, redis: Any, manager: Any, limit: int = 40, offset: int = 0) -> dict[str, Any]:
        msgs = await Cacher.get_messages(session_id, redis, manager, limit=limit, offset=offset)
        return {"messages": msgs}

    @staticmethod
    async def download_chat(session_id: str, redis: Any, manager: Any) -> PlainTextResponse:
        history = await Cacher.get_messages(session_id, redis, manager)
        content = f"--- 대화 기록 ({session_id}) ---\n"
        for msg in history:
            role = "사용자" if msg.get("sender_type") == "user" else "봇"
            content += f"[{role}]\n{msg.get('content', '')}\n\n"
        return PlainTextResponse(content, headers={"Content-Disposition": f"attachment; filename=chat_{session_id}.txt"})

    @staticmethod
    async def get_session_info(redis: Any, manager: Any, session_id: str) -> dict[str, Any]:
        return await Cacher.get_session_info(session_id, redis, manager)

    @staticmethod
    async def move_session_to_trip(redis: Any, manager: Any, session_id: str, trip_id: Optional[str], user_id: str) -> dict[str, Any]:
        return await Cacher.move_session_to_trip(session_id, trip_id, user_id, redis, manager)

    @staticmethod
    async def mark_session_read(redis: Any, manager: Any, session_id: str, user_id: str) -> None:
        await Cacher.mark_session_read(session_id, user_id, redis, manager)

    @staticmethod
    async def search_users(redis: Any, manager: Any, q: str, user_id: str) -> dict[str, Any]:
        return await Cacher.search_users(q, user_id, redis, manager)

    @staticmethod
    async def upload_files(session_id: str, files: List[UploadFile], user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        up_dir = os.path.join(base, "uploads", session_id, user_id)
        os.makedirs(up_dir, exist_ok=True)

        names = []
        for file in files:
            safe_name = os.path.basename(file.filename or "upload")
            dest = os.path.join(up_dir, safe_name)
            with open(dest, "wb+") as f:
                f.write(await file.read())
            names.append(safe_name)

        if names:
            await ChatService._save_file_message(session_id, user_id, names, redis, manager)
        return {"success": True, "uploaded_files": names}

    @staticmethod
    async def _save_file_message(session_id: str, user_id: str, names: list[str], redis: Any, manager: Any) -> None:
        profile = await Cacher.get_user_profile(user_id, redis, manager)
        sender_name = (profile.get("nickname") or "").strip() or "사용자"
        now = datetime.now(tz=timezone.utc)
        msg_id = "msg_" + str(uuid.uuid4())[:12]
        content = f"[파일 첨부] {', '.join(names)}"

        await Cacher.save_message(session_id, {
            "message_id": msg_id,
            "session_id": session_id,
            "sender_id": user_id,
            "sender_name": sender_name,
            "sender_type": "user",
            "message_type": "file",
            "content": content,
            "created_at": now.isoformat(),
        }, redis, manager)

        NotifyService.push_to_session(session_id, json.dumps({
            "type": "message",
            "sender_id": user_id,
            "sender_name": sender_name,
            "content": content,
            "msg_id": msg_id,
            "ts": now.isoformat(),
            "msg_type": "file",
            "files": names,
        }, ensure_ascii=False))
