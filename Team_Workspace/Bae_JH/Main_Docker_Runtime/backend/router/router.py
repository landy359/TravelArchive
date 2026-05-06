"""
router.py
세션과 관련된 모든 로직.

facade.py 의 각 라우트 함수가 직접 구현 대신 이 클래스를 호출합니다.
  Router.*  — 세션 생명주기, 메시지, 지도, 메모, 플래너, 파일 등 모든 세션 작업

데이터 저장 구조:
  - 세션 메타/대화 기록  → Postgres (Sessions, Conversations 테이블)
  - 세션 메타 캐시       → Redis  (session:{id}:meta)
  - 지도/메모/플랜/기간  → Redis  (session:{id}:markers 등, TTL 24h)
  - 임시 세션           → 프로세스 메모리 (_temp_sessions)
"""

import os
import uuid
import json
import asyncio
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import UploadFile
from fastapi.responses import StreamingResponse, PlainTextResponse

from ..session_container import SessionContainer
from ..system.db_interface import PostgresDBInterface
from ..system.session_cache import SessionCache
from ..system.flush_service import FlushService


# ── 인메모리 SessionContainer 풀 ────────────────────────────
_active_sessions: Dict[str, SessionContainer] = {}

# ── 비로그인 임시 세션 (DB 저장 없음) ──────────────────────
_temp_sessions:   Dict[str, SessionContainer] = {}

# ── 팀 채팅 SSE 구독 큐 ─────────────────────────────────────
# session_id → [asyncio.Queue, ...]  (각 클라이언트 연결마다 Queue 1개)
_session_sse_queues: Dict[str, List[asyncio.Queue]] = {}

# queue id(q) → user_id  (타이핑 자기 자신 제외용)
_queue_to_user: Dict[int, str] = {}

# ── 사용자별 알림 SSE 큐 ──────────────────────────────────────
# user_id → [asyncio.Queue, ...]
_user_notif_queues: Dict[str, List[asyncio.Queue]] = {}

# MockDBInterface (임시 세션 전용)
class _MockDB:
    async def load_personalization(self, user_id): return ""
    async def load_session_data(self, session_id): return {}
    async def append_messages(self, session_id, messages): pass
    async def save_session_state(self, session_id, topic, name, context, is_manual_title): pass
    async def get_chat_history(self, session_id): return []


# ============================================================
# Router
# ============================================================

class Router:

    # ── 비로그인 임시 챗봇 ──────────────────────────────────

    @staticmethod
    async def send_temp_message(temp_session_id: str, message: str) -> StreamingResponse:
        """비로그인 또는 로그인 후 임시채팅 전용. DB/Redis 저장 없음."""
        if temp_session_id not in _temp_sessions:
            container = SessionContainer(
                session_id=temp_session_id,
                user_id="TEMP",
                db_interface=_MockDB(),
            )
            await container.initialize_session(is_new=True)
            _temp_sessions[temp_session_id] = container

        container = _temp_sessions[temp_session_id]

        async def _stream():
            response_text = await container.process_user_input(message)
            for char in response_text:
                yield char
                await asyncio.sleep(0.03)

        return StreamingResponse(_stream(), media_type="text/plain")

    # ── 여행(Trip) 목록 — facade에서 Loader 직접 호출 후 반환 ─

    @staticmethod
    async def get_trip_list(postgres, user_id: str) -> dict:
        from ..loader.loader import Loader
        trips = await Loader.get_trip_list(postgres, user_id)
        return {"trips": trips}

    # ── 세션 목록 ────────────────────────────────────────────

    @staticmethod
    async def get_session_list(trip_id: Optional[str], user_id: str, postgres) -> dict:
        from ..loader.loader import Loader
        sessions = await Loader.get_session_list(postgres, user_id, trip_id)
        return {"sessions": sessions}

    # ── 세션 생성 ────────────────────────────────────────────

    @staticmethod
    async def create_session(first_message: str, mode: str, user_id: str,
                              trip_id: Optional[str], postgres, redis) -> dict:
        session_id = "session_" + str(uuid.uuid4())[:8]
        title      = first_message[:20] + "..." if len(first_message) > 20 else first_message
        today      = date.today().isoformat()

        from ..loader.loader import Loader

        # trip_id 없으면 기타 trip에 귀속
        if not trip_id:
            trip_id = await Loader.ensure_misc_trip(postgres, user_id)

        await Loader.create_session_record(postgres, session_id, user_id, {
            "title":   title,
            "trip_id": trip_id,
        })

        # trip color 조회
        trip_color = None
        trips = await Loader.get_trip_list(postgres, user_id)
        for t in trips:
            if t.get("trip_id") == trip_id:
                trip_color = t.get("color")
                break

        return {
            "id":                session_id,
            "title":             title,
            "trip_id":           trip_id,
            "trip_color":        trip_color,
            "user_id":           user_id,
            "created_at":        today,
            "participant_count": 1,
            "user_role":         "master",
        }

    # ── 세션 탈퇴 (팀원 본인) ────────────────────────────────

    @staticmethod
    async def leave_session(session_id: str, user_id: str, postgres, redis) -> dict:
        """비마스터 팀원이 본인 탈퇴."""
        from ..loader.loader import Loader
        await Loader.leave_session(postgres, session_id, user_id)
        await SessionCache.unmark_active(user_id, session_id, redis)
        return {"success": True}

    # ── 세션 탈퇴 (마스터) ──────────────────────────────────

    @staticmethod
    async def delete_session(session_id: str, user_id: str,
                              postgres, redis) -> dict:
        """
        마스터가 세션에서 나감.
        - 팀원이 있으면 가장 오래된 팀원이 마스터 승계, SSE로 new_master 이벤트 전송.
        - 팀원이 없으면 세션 삭제(비활성화).
        """
        from ..loader.loader import Loader
        result = await Loader.leave_as_master(postgres, session_id, user_id)

        await SessionCache.unmark_active(user_id, session_id, redis)

        if result["deleted"]:
            # 아무도 없어서 세션 삭제 — SSE 큐에 kicked 전송 (혹시 남은 연결 있다면)
            kicked_event = json.dumps({
                "type":       "kicked",
                "session_id": session_id,
                "reason":     "session_deleted",
            }, ensure_ascii=False)
            for q in list(_session_sse_queues.get(session_id, [])):
                try:
                    q.put_nowait(kicked_event)
                except asyncio.QueueFull:
                    pass

            if session_id in _active_sessions:
                try:
                    await _active_sessions[session_id].teardown()
                except Exception:
                    pass
                del _active_sessions[session_id]
            await FlushService.flush_single_session(session_id, postgres, redis)
        else:
            # 마스터 승계 — 새 마스터 ID를 SSE로 알림
            new_master_event = json.dumps({
                "type":       "new_master",
                "session_id": session_id,
                "user_id":    result["new_master"],
            }, ensure_ascii=False)
            for q in list(_session_sse_queues.get(session_id, [])):
                try:
                    q.put_nowait(new_master_event)
                except asyncio.QueueFull:
                    pass

        return {"success": True, "deleted": result["deleted"]}

    # ── 개인 전환 (마스터 전용) ──────────────────────────────

    @staticmethod
    async def convert_to_personal(session_id: str, user_id: str,
                                   postgres, redis) -> dict:
        """마스터 전용: 팀원 전원 퇴장 후 개인 세션으로 전환(참여자 수 = 1)."""
        from ..loader.loader import Loader
        from fastapi import HTTPException
        role = await Loader.get_session_role(postgres, session_id, user_id)
        if role != "master":
            raise HTTPException(status_code=403, detail="마스터만 개인 전환을 할 수 있습니다")

        # 팀원에게 kicked 이벤트 브로드캐스트
        kicked_event = json.dumps({
            "type":       "kicked",
            "session_id": session_id,
            "reason":     "master_converted_to_personal",
        }, ensure_ascii=False)
        for q in list(_session_sse_queues.get(session_id, [])):
            try:
                q.put_nowait(kicked_event)
            except asyncio.QueueFull:
                pass

        # DB에서 마스터 외 전원 제거
        await postgres.execute({
            "action": "raw_sql",
            "sql": "DELETE FROM session_participants WHERE session_id = :sid AND role NOT IN ('master', 'bot')",
            "params": {"sid": session_id},
        })
        return {"success": True}

    # ── 세션 제목 변경 ────────────────────────────────────────

    @staticmethod
    async def update_session_title(session_id: str, title: str, user_id: str,
                                    postgres, redis) -> dict:
        # Redis 메타 갱신
        meta = await SessionCache.get_session_meta(session_id, redis) or {}
        meta["name"] = title
        meta["is_manual_title"] = "true"
        await SessionCache.cache_session_meta(session_id, meta, redis)

        # 활성 컨테이너에도 반영
        if session_id in _active_sessions:
            _active_sessions[session_id].session_name  = title
            _active_sessions[session_id].is_manual_title = True

        # Postgres 갱신
        from ..loader.loader import Loader
        await Loader.update_session_record(postgres, session_id, {
            "title":           title,
            "is_manual_title": True,
        })

        # 팀 세션 구독자에게 제목 변경 이벤트 브로드캐스트
        event_data = json.dumps({
            "type":       "title_updated",
            "session_id": session_id,
            "title":      title,
        }, ensure_ascii=False)
        for q in list(_session_sse_queues.get(session_id, [])):
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                pass

        return {"success": True, "title": title}

    # ── 세션 색상 변경 ───────────────────────────────────────

    @staticmethod
    async def update_session_color(session_id: str, color: str, user_id: str,
                                    postgres) -> dict:
        from ..loader.loader import Loader
        await Loader.update_session_record(postgres, session_id, {"color": color})
        return {"success": True, "color": color}

    # ── 세션 초대 ────────────────────────────────────────────

    @staticmethod
    async def invite_user(session_id: str, invitee: str, user_id: str,
                           postgres) -> dict:
        from ..loader.loader import Loader
        return await Loader.invite_to_session(postgres, session_id, user_id, invitee)

    # ── 채팅 공유 ────────────────────────────────────────────

    @staticmethod
    async def share_chat(session_id: str, user_id: str) -> dict:
        return {"success": True, "share_url": f"/share/{session_id}"}

    # ── 메시지 전송 ──────────────────────────────────────────

    @staticmethod
    async def send_message(session_id: str, message: str, user_id: str,
                            postgres, redis) -> StreamingResponse:
        """모든 세션(개인/팀)에서 AI 없이 메시지 저장 + 팀일 때만 SSE 브로드캐스트."""
        return await Router._handle_session_message(session_id, user_id, message, postgres)

    @staticmethod
    async def _handle_session_message(session_id: str, user_id: str,
                                       message: str, postgres) -> StreamingResponse:
        """모든 세션: AI 없이 메시지 DB 저장. 팀 세션은 SSE 브로드캐스트 + 미열람자 알림."""
        now    = datetime.now(tz=timezone.utc)
        msg_id = "msg_" + str(uuid.uuid4())[:12]

        await postgres.execute({
            "action": "create", "model": "Conversation",
            "data": {
                "message_id":   msg_id,
                "session_id":   session_id,
                "sender_id":    user_id,
                "sender_type":  "user",
                "message_type": "text",
                "content":      message,
                "created_at":   now,
            },
        })

        # 발신자 닉네임 조회
        nr = await postgres.execute({
            "action": "raw_sql",
            "sql": "SELECT nickname FROM user_profile WHERE user_id = :uid",
            "params": {"uid": user_id},
        })
        sender_name = (nr.get("data") or [{}])[0].get("nickname", user_id)

        # 세션 참여자 목록 (발신자 제외)
        pr = await postgres.execute({
            "action": "raw_sql",
            "sql": "SELECT user_id FROM session_participants WHERE session_id = :sid AND user_id != :uid",
            "params": {"sid": session_id, "uid": user_id},
        })
        other_participants = [r["user_id"] for r in pr.get("data", [])]
        is_team = len(other_participants) > 0

        # @멘션 감지 후 해당 사용자에게 알림 push
        import re as _re
        mentions = _re.findall(r'@(\S+)', message)
        if mentions:
            for mention_nick in set(mentions):
                mr = await postgres.execute({
                    "action": "raw_sql",
                    "sql": "SELECT user_id FROM user_profile WHERE nickname = :nick",
                    "params": {"nick": mention_nick},
                })
                for row in mr.get("data", []):
                    target_uid = row.get("user_id")
                    if target_uid and target_uid != user_id:
                        notif_id = "notif_" + str(uuid.uuid4())[:12]
                        await postgres.execute({
                            "action": "create", "model": "Notification",
                            "data": {
                                "notification_id": notif_id,
                                "user_id":         target_uid,
                                "type":            "mention",
                                "reference_type":  "session",
                                "reference_id":    session_id,
                                "message":         f"{sender_name}님이 '@{mention_nick}'님을 언급했습니다",
                                "is_read":         False,
                                "created_at":      now,
                            },
                        })
                        await Router.push_notification_to_user(target_uid, {
                            "sub_type":   "mention",
                            "message":    f"{sender_name}님이 '@{mention_nick}'님을 언급했습니다",
                            "session_id": session_id,
                        })

        # 팀 세션: SSE 브로드캐스트 + 미열람 참여자에게 new_message 알림
        if is_team:
            event_data = json.dumps({
                "type":        "message",
                "sender_id":   user_id,
                "sender_name": sender_name,
                "content":     message,
                "msg_id":      msg_id,
                "ts":          now.isoformat(),
            }, ensure_ascii=False)

            for q in list(_session_sse_queues.get(session_id, [])):
                try:
                    q.put_nowait(event_data)
                except asyncio.QueueFull:
                    pass

            # SSE를 구독 중이지 않은(= 세션을 열어보지 않고 있는) 참여자에게 알림 push
            viewing_user_ids = {
                _queue_to_user.get(id(q))
                for q in _session_sse_queues.get(session_id, [])
            }
            for other_uid in other_participants:
                if other_uid not in viewing_user_ids:
                    await Router.push_notification_to_user(other_uid, {
                        "sub_type":    "new_message",
                        "message":     f"{sender_name}: {message[:50]}",
                        "session_id":  session_id,
                    })

        # ── @BOT 감지: LLM 응답 스트리밍 ──────────────────────
        import re as _re2
        bot_match = _re2.match(r'^@BOT\s+([\s\S]+)', message, _re2.IGNORECASE)
        if bot_match:
            bot_query = bot_match.group(1).strip()
            return await Router._stream_bot_response(session_id, bot_query, postgres, user_id)

        async def _ack():
            yield b''

        return StreamingResponse(_ack(), media_type="text/plain")

    # 하위 호환: facade.py의 team-message 엔드포인트에서 참조
    _handle_team_message = _handle_session_message

    @staticmethod
    async def _stream_bot_response(session_id: str, query: str, postgres,
                                    triggering_user_id: str = None) -> StreamingResponse:
        """LLM을 호출해 응답을 스트리밍하고, DB 저장 + SSE 브로드캐스트.
        triggering_user_id의 SSE 큐는 건너뜀 (HTTP 스트림으로 이미 수신)."""
        from ..test_agent import TestNode
        from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY, GENERATION_PROMPT

        # 최근 대화 컨텍스트 (최대 10건)
        hr = await postgres.execute({
            "action": "raw_sql",
            "sql": "SELECT sender_type, content FROM conversations WHERE session_id = :sid ORDER BY created_at DESC LIMIT 10",
            "params": {"sid": session_id},
        })
        recent = list(reversed(hr.get("data", [])))
        past_chat = "\n".join(
            ("사용자" if m["sender_type"] == "user" else "AI") + ": " + m["content"]
            for m in recent
        ) or "최근 대화 내역 없음"

        prompt = GENERATION_PROMPT.format(
            p_topic="",
            s_topic="여행 대화",
            s_context="",
            past_chat_history=past_chat,
            current_msg_content=query,
        )
        node = TestNode(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY)

        async def _stream():
            bot_text = await node.ask(prompt)

            # DB 저장
            bot_now    = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await postgres.execute({
                "action": "create", "model": "Conversation",
                "data": {
                    "message_id":   bot_msg_id,
                    "session_id":   session_id,
                    "sender_id":    None,
                    "sender_type":  "ai",
                    "message_type": "text",
                    "content":      bot_text,
                    "created_at":   bot_now,
                },
            })

            # SSE 브로드캐스트 — 트리거한 유저의 큐는 제외 (이미 HTTP 스트림으로 수신 중)
            sse_event = json.dumps({
                "type":        "message",
                "sender_id":   "bot",
                "sender_name": "AI",
                "content":     bot_text,
                "msg_id":      bot_msg_id,
                "ts":          bot_now.isoformat(),
            }, ensure_ascii=False)
            for q in list(_session_sse_queues.get(session_id, [])):
                if triggering_user_id and _queue_to_user.get(id(q)) == triggering_user_id:
                    continue
                try:
                    q.put_nowait(sse_event)
                except asyncio.QueueFull:
                    pass

            # 문자 단위 스트리밍
            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    # ── 타이핑 인디케이터 (비활성화) ─────────────────────────

    @staticmethod
    async def broadcast_typing(session_id: str, user_id: str, postgres) -> dict:
        return {"success": True}

    # ── 팀 채팅 SSE 구독 ─────────────────────────────────────

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

    # ── 사용자별 알림 SSE ────────────────────────────────────

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
    async def push_notification_to_user(user_id: str, notif_data: dict):
        """팀 초대 등 이벤트 발생 시 해당 사용자 알림 큐에 push."""
        event_data = json.dumps({"type": "notification", **notif_data}, ensure_ascii=False)
        for q in list(_user_notif_queues.get(user_id, [])):
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                pass

    # ── 대화 기록 조회 ────────────────────────────────────────

    @staticmethod
    async def get_chat_history(session_id: str, postgres,
                               limit: int = 40, offset: int = 0) -> dict:
        from ..loader.loader import Loader
        msgs = await Loader.get_conversation_history(postgres, session_id,
                                                     limit=limit, offset=offset)
        return {"messages": msgs}

    # ── 대화 다운로드 ────────────────────────────────────────

    @staticmethod
    async def download_chat(session_id: str, postgres) -> PlainTextResponse:
        from ..loader.loader import Loader
        history = await Loader.get_conversation_history(postgres, session_id)

        content = f"--- 대화 기록 ({session_id}) ---\n"
        for msg in history:
            role = "사용자" if msg.get("role") == "user" else "봇"
            content += f"[{role}]\n{msg.get('content', '')}\n\n"

        headers = {"Content-Disposition": f"attachment; filename=chat_{session_id}.txt"}
        return PlainTextResponse(content, headers=headers)

    # ── 파일 업로드 ──────────────────────────────────────────

    @staticmethod
    async def upload_files(session_id: str, files: List[UploadFile],
                            user_id: str, postgres=None) -> dict:
        base   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # 세션/사용자별 폴더 분리 (#18)
        up_dir = os.path.join(base, "uploads", session_id, user_id)
        os.makedirs(up_dir, exist_ok=True)

        names = []
        for file in files:
            safe_name = os.path.basename(file.filename or "upload")
            dest = os.path.join(up_dir, safe_name)
            with open(dest, "wb+") as f:
                f.write(await file.read())
            names.append(safe_name)

        if postgres and names:
            # 발신자 닉네임 조회
            nr = await postgres.execute({
                "action": "raw_sql",
                "sql": "SELECT nickname FROM user_profile WHERE user_id = :uid",
                "params": {"uid": user_id},
            })
            sender_name = (nr.get("data") or [{}])[0].get("nickname", user_id)

            now    = datetime.now(tz=timezone.utc)
            msg_id = "msg_" + str(uuid.uuid4())[:12]
            content = f"[파일 첨부] {', '.join(names)}"

            await postgres.execute({
                "action": "create", "model": "Conversation",
                "data": {
                    "message_id":   msg_id,
                    "session_id":   session_id,
                    "sender_id":    user_id,
                    "sender_type":  "user",
                    "message_type": "file",
                    "content":      content,
                    "created_at":   now,
                },
            })

            event_data = json.dumps({
                "type":        "message",
                "sender_id":   user_id,
                "sender_name": sender_name,
                "content":     content,
                "msg_id":      msg_id,
                "ts":          now.isoformat(),
                "msg_type":    "file",
                "files":       names,
            }, ensure_ascii=False)

            for q in list(_session_sse_queues.get(session_id, [])):
                try:
                    q.put_nowait(event_data)
                except asyncio.QueueFull:
                    pass

        return {"success": True, "uploaded_files": names}

    # ── 지도 마커 (Redis) ────────────────────────────────────

    @staticmethod
    async def add_map_marker(session_id: str, marker_id: str,
                              lat: float, lng: float, title: str,
                              user_id: str, redis) -> dict:
        markers = await SessionCache.get_markers(session_id, redis)
        markers = [m for m in markers if m.get("marker_id") != marker_id]
        markers.append({"marker_id": marker_id, "lat": lat, "lng": lng, "title": title})
        await SessionCache.save_markers(session_id, markers, redis)
        return {"success": True, "marker_id": marker_id}

    @staticmethod
    async def delete_map_marker(session_id: str, marker_id: str,
                                 user_id: str, redis) -> dict:
        markers = await SessionCache.get_markers(session_id, redis)
        markers = [m for m in markers if m.get("marker_id") != marker_id]
        await SessionCache.save_markers(session_id, markers, redis)
        return {"success": True}

    @staticmethod
    async def save_map_markers(session_id: str, markers: List[dict],
                                user_id: str, redis) -> dict:
        normalized = []
        for m in markers:
            mid = m.get("marker_id") or m.get("id")
            if mid:
                normalized.append({
                    "marker_id": mid,
                    "lat":       m.get("lat", 0),
                    "lng":       m.get("lng", 0),
                    "title":     m.get("title", ""),
                })
        await SessionCache.save_markers(session_id, normalized, redis)
        return {"success": True}

    @staticmethod
    async def get_map_markers(session_id: str, user_id: str, redis) -> dict:
        markers = await SessionCache.get_markers(session_id, redis)
        return {"markers": markers}

    # ── 폴리라인 경로 (Redis: 정점 순서만 저장) ──────────────

    @staticmethod
    async def save_map_routes(session_id: str, marker_ids: List[str],
                               user_id: str, redis) -> dict:
        await SessionCache.save_routes(session_id, marker_ids, redis)
        return {"success": True}

    @staticmethod
    async def get_map_routes(session_id: str, user_id: str, redis) -> dict:
        marker_ids = await SessionCache.get_routes(session_id, redis)
        return {"marker_ids": marker_ids}

    # ── 여행 기간 (Redis) ────────────────────────────────────

    @staticmethod
    async def save_trip_range(session_id: str, ranges: List[dict],
                               user_id: str, redis) -> dict:
        await SessionCache.save_ranges(session_id, ranges, redis)
        return {"success": True}

    @staticmethod
    async def get_trip_range(session_id: str, user_id: str, redis) -> dict:
        ranges = await SessionCache.get_ranges(session_id, redis)
        return {"ranges": ranges}

    # ── 메모 (Redis) ─────────────────────────────────────────

    @staticmethod
    async def save_memo(session_id: str, date_key: str, memo: str,
                         user_id: str, redis) -> dict:
        await SessionCache.save_memo(session_id, date_key, memo, redis)
        return {"success": True}

    @staticmethod
    async def get_memo(session_id: str, date_key: str, user_id: str, redis) -> dict:
        memo = await SessionCache.get_memo(session_id, date_key, redis)
        return {"memo": memo}

    # ── 플래너 (Redis) ───────────────────────────────────────

    @staticmethod
    async def save_plan(session_id: str, date_key: str, plan: List[dict],
                         user_id: str, redis) -> dict:
        await SessionCache.save_plan(session_id, date_key, plan, redis)
        return {"success": True}

    @staticmethod
    async def get_plan(session_id: str, date_key: str, user_id: str, redis) -> dict:
        plan = await SessionCache.get_plan(session_id, date_key, redis)
        return {"plan": plan}

    # ── 캘린더 인디케이터 (Redis) ────────────────────────────

    @staticmethod
    async def get_indicators(session_id: str, year: int, month: int,
                              user_id: str, redis) -> list:
        return await SessionCache.get_indicators(session_id, year, month, redis)
