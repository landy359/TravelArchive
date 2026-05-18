"""chat_service.py  [domain / chat 카테고리]

역할:
  대화와 관련된 인프라 전반 — 세션 생명주기·메시지 전송·파일·기록·공유.
  PG 접근은 Cacher → manager(EventHandler) 경로만 사용한다.
"""

import asyncio
import json
import os
import re as _re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from ...memory.cacher import Cacher
from ..system.system_notify import NotifyService
from .chat_flush_service import FlushService
from .chat_session_container import SessionContainer

_temp_sessions: Dict[str, SessionContainer] = {}


class ChatService:

    @staticmethod
    async def send_temp_message(temp_session_id: str, message: str) -> StreamingResponse:
        """비로그인 임시채팅 전용. DB/Redis 저장 없음."""
        if temp_session_id not in _temp_sessions:
            _temp_sessions[temp_session_id] = SessionContainer(session_id=temp_session_id, user_id="TEMP")
        container = _temp_sessions[temp_session_id]

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
    async def create_session(first_message: str, mode: Optional[str], user_id: str, trip_id: Optional[str], redis: Any, manager: Any) -> dict[str, Any]:
        session_id = "session_" + str(uuid.uuid4())[:8]
        title = first_message[:20] + "..." if len(first_message) > 20 else first_message
        if not trip_id:
            trip_id = await Cacher.ensure_misc_trip(user_id, redis, manager)

        await Cacher.create_session(session_id, user_id, {"title": title, "trip_id": trip_id}, redis, manager)

        trip_color = None
        for trip in await Cacher.get_trip_list(user_id, redis, manager):
            if trip.get("trip_id") == trip_id:
                trip_color = trip.get("color")
                break

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
        await Cacher.leave_session(session_id, user_id, redis, manager)
        return {"success": True}

    @staticmethod
    async def delete_session(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        result = await Cacher.leave_as_master(session_id, user_id, redis, manager)
        if result["deleted"]:
            NotifyService.push_to_session(session_id, json.dumps({
                "type": "kicked",
                "session_id": session_id,
                "reason": "session_deleted",
            }, ensure_ascii=False))
            await FlushService.flush_single_session(session_id, redis, manager)
        else:
            NotifyService.push_to_session(session_id, json.dumps({
                "type": "new_master",
                "session_id": session_id,
                "user_id": result["new_master"],
            }, ensure_ascii=False))
        return {"success": True, "deleted": result["deleted"]}

    @staticmethod
    async def convert_to_personal(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, bool]:
        from fastapi import HTTPException

        role = await Cacher.get_session_role(session_id, user_id, redis, manager)
        if role != "master":
            raise HTTPException(status_code=403, detail="마스터만 개인 전환을 할 수 있습니다")

        NotifyService.push_to_session(session_id, json.dumps({
            "type": "kicked",
            "session_id": session_id,
            "reason": "master_converted_to_personal",
        }, ensure_ascii=False))
        await Cacher.remove_non_master_participants(session_id, redis, manager)
        return {"success": True}

    @staticmethod
    async def update_session_title(session_id: str, title: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        meta = await Cacher.get_session_meta(session_id, redis) or {}
        meta["name"] = title
        meta["is_manual_title"] = "true"
        await Cacher.cache_session_meta(session_id, meta, redis)
        await Cacher.update_session_record(session_id, {"title": title, "is_manual_title": True}, redis, manager)
        NotifyService.push_to_session(session_id, json.dumps({
            "type": "title_updated",
            "session_id": session_id,
            "title": title,
        }, ensure_ascii=False))
        return {"success": True, "title": title}

    @staticmethod
    async def update_session_color(session_id: str, color: str, user_id: str, redis: Any, manager: Any) -> dict[str, str]:
        await Cacher.update_session_record(session_id, {"color": color}, redis, manager)
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

        await Cacher.save_message(session_id, {
            "message_id": msg_id,
            "session_id": session_id,
            "sender_id": user_id,
            "sender_type": "user",
            "message_type": "text",
            "content": message,
            "created_at": now.isoformat(),
        }, redis, manager)

        profile = await Cacher.get_user_profile(user_id, redis, manager)
        sender_name = profile.get("nickname", user_id)
        participants = await Cacher.get_session_participants(session_id, redis, manager)
        other_ids = [p["user_id"] for p in participants if p.get("user_id") != user_id and p.get("user_id") != "bot"]
        is_team = len(other_ids) > 0

        await ChatService._notify_mentions(session_id, user_id, sender_name, message, now, redis, manager)
        if is_team:
            ChatService._broadcast_user_message(session_id, user_id, sender_name, message, msg_id, now)
            ChatService._push_unviewed_user_notices(session_id, other_ids, sender_name, message)

        if not is_team:
            bot_query = _re.sub(r'^@BOT\s+', '', message, flags=_re.IGNORECASE).strip()
            return await ChatService._stream_bot_response(session_id, bot_query, message, user_id, redis, manager)

        bot_match = _re.match(r'^@BOT\s+([\s\S]+)', message, _re.IGNORECASE)
        if bot_match:
            return await ChatService._stream_bot_response(session_id, bot_match.group(1).strip(), message, user_id, redis, manager)

        asyncio.create_task(ChatService._run_ingest(session_id, user_id, message, redis))

        async def _ack():
            yield b''

        return StreamingResponse(_ack(), media_type="text/plain")

    _handle_team_message = _handle_session_message

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
    async def _run_ingest(session_id: str, user_id: str, message: str, redis: Any) -> None:
        """백그라운드: SessionContainer에 메시지를 등록하고 주제를 추론."""
        try:
            container = await ChatService._get_container(session_id, user_id, redis)
            title_changed = await container.ingest_message(message)
            if title_changed:
                NotifyService.push_to_session(session_id, json.dumps({
                    "type": "title_updated",
                    "session_id": session_id,
                    "title": container.session_name,
                }, ensure_ascii=False))
        except Exception as e:
            print(f"[ChatService._run_ingest] {session_id} 오류: {e}")

    @staticmethod
    async def _stream_bot_response(session_id: str, query: str, full_message: str, triggering_user_id: str, redis: Any, manager: Any) -> StreamingResponse:
        """ingest(주제추론) → generate(LLM응답) 순서로 처리하고 저장 + SSE 브로드캐스트."""

        async def _stream():
            try:
                container = await ChatService._get_container(session_id, triggering_user_id, redis)
                title_changed = await container.ingest_message(full_message)
                if title_changed:
                    NotifyService.push_to_session(session_id, json.dumps({
                        "type": "title_updated",
                        "session_id": session_id,
                        "title": container.session_name,
                    }, ensure_ascii=False))
                bot_text = await container.generate_bot_response(query)
            except Exception as e:
                print(f"[ChatService._stream_bot_response] {session_id} 오류: {e}")
                bot_text = "죄송합니다, 응답을 생성할 수 없습니다."

            bot_now = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id": bot_msg_id,
                "session_id": session_id,
                "sender_id": None,
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
        sender_name = profile.get("nickname", user_id)
        now = datetime.now(tz=timezone.utc)
        msg_id = "msg_" + str(uuid.uuid4())[:12]
        content = f"[파일 첨부] {', '.join(names)}"

        await Cacher.save_message(session_id, {
            "message_id": msg_id,
            "session_id": session_id,
            "sender_id": user_id,
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
