"""chat_service.py  [domain / chat 카테고리]

역할:
  대화와 관련된 인프라 전반 — 세션 생명주기·메시지 전송·파일·기록·공유.
  PG 접근은 Cacher → manager(EventHandler) 경로만 사용한다.
"""

import asyncio
import base64
import json
import os
import re as _re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from ...memory.cacher import Cacher
from ..system.system_notify import NotifyService
from .chat_flush_service import FlushService
from .chat_session_container import SessionContainer

# 임시 세션 저장소 — (container, last_access_ts) 쌍으로 보관
_temp_sessions: Dict[str, tuple[SessionContainer, float]] = {}
_TEMP_SESSION_TTL = 3600  # 1시간 미사용 시 제거
_MAX_TEMP_SESSIONS = 200
_BACKGROUND_TASKS: set[asyncio.Task] = set()  # create_task GC 방지

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _format_weather_raw(items) -> str:
    """dDB_Item 리스트 → LLM 입력·스냅샷 비교용 원시 텍스트."""
    from collections import defaultdict
    by_date: dict = defaultdict(list)
    for w in items:
        by_date[w.forecast_date].append(w)
    lines = []
    for date_key in sorted(by_date):
        day_items = sorted(by_date[date_key], key=lambda x: x.forecast_time)
        mm, dd = date_key[4:6], date_key[6:8]
        lines.append(f"\n{mm}월 {dd}일")
        for w in day_items:
            rain = f", 강수확률 {w.rain_prob}%" if w.rain_prob else ""
            lines.append(f"  {w.forecast_time}시: {w.summary}, 기온 {w.temperature}°C{rain}")
    return "\n".join(lines).strip() or "날씨 정보가 없습니다."


_WEATHER_SUMMARY_PROMPT = (
    "너는 여행 날씨 안내 도우미야. 아래 날씨 데이터를 여행자를 위해 자연스럽고 친절하게 요약해줘.\n"
    "규칙:\n"
    "- 날짜별로 한 줄~두 줄. 시간대별 나열 절대 금지.\n"
    "- 대표 기온(최저~최고 범위)과 날씨 개황만 간결하게.\n"
    "- 강수확률 20% 이상인 날은 우산 준비 한마디 추가.\n"
    "- '중기예보' 표시 날짜는 마지막에 '(중기예보 기준, 실제와 다를 수 있음)' 한 번만 표시.\n"
    "- 영어 단어 절대 금지. 순한국어만.\n"
    "- 전체 100~200자 이내.\n"
    "\n[날씨 데이터]\n{raw}"
)


async def _summarize_weather_with_llm(raw_text: str) -> str:
    """날씨 원시 텍스트 → LLM 자연어 요약."""
    from ...kernel.llm import LLM
    from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY
    prompt = _WEATHER_SUMMARY_PROMPT.format(raw=raw_text)
    try:
        result = await LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY).ask(prompt)
        return result.strip() if result and not result.startswith("ERROR:") else raw_text
    except Exception as e:
        print(f"[WeatherService] LLM 요약 실패: {e}", flush=True)
        return raw_text


async def _save_weather_snapshot(session_id: str, owner_id: str, t_cd: list, ssn_tpc: str, ddb_items, redis) -> None:
    """날씨 스냅샷 저장. 24h 변화 감지 스케줄러용."""
    snapshot = {
        "session_id": session_id,
        "owner_id":   owner_id,
        "t_cd":       t_cd,
        "ssn_tpc":    ssn_tpc,
        "entries": [
            {
                "date":        w.forecast_date,
                "time":        w.forecast_time,
                "summary":     w.summary,
                "rain_prob":   w.rain_prob,
                "temperature": w.temperature,
            }
            for w in ddb_items
        ],
    }
    await redis.set_json(f"session:{session_id}:weather_snapshot", snapshot, 2592000)
    await redis.execute({"action": "sadd", "key": "weather_snapshots:sessions", "member": session_id})


async def _maybe_notify_response_complete(session_id: str, user_id: str, redis: Any, manager: Any) -> None:
    """AI 응답 완료 시 요청자에게 알림 push (설정 '응답 완료시 알림' ON일 때만).

    창 최소화·다른 세션·다른 탭에 있어도 SSE 알림 큐로 전달되어
    뱃지/브라우저 알림으로 완료를 알린다. 본인 opt-in 토글(기본 OFF)로 게이트.
    """
    if not user_id:
        return
    try:
        ui = await Cacher.get_ui_settings(user_id, redis)
        notif_cfg = ui.get("notifications") if isinstance(ui, dict) else None
        if not (isinstance(notif_cfg, dict) and notif_cfg.get("response")):
            return
        notif_id = "notif_" + str(uuid.uuid4())[:12]
        message  = "AI 응답이 완료되었습니다."
        notif_data = {
            "notification_id": notif_id,
            "user_id":         user_id,
            "type":            "response_complete",
            "reference_type":  "session",
            "reference_id":    session_id,
            "message":         message,
            "is_read":         False,
            "created_at":      datetime.now(tz=timezone.utc).isoformat(),
        }
        await Cacher.save_notification(user_id, notif_data, redis, manager)
        NotifyService.push_to_user(user_id, {
            "sub_type":   "response_complete",
            "message":    message,
            "session_id": session_id,
        })
    except Exception as _e:
        print(f"[ResponseNotify] {session_id} 알림 실패: {_e}", flush=True)
_EXT_TO_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}


def _read_image_payload(img_path: str, mime: str) -> tuple[str, str]:
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


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
        if temp_session_id not in _temp_sessions and len(_temp_sessions) >= _MAX_TEMP_SESSIONS:
            raise HTTPException(status_code=429, detail="서버가 혼잡합니다. 잠시 후 다시 시도해주세요")
        if temp_session_id not in _temp_sessions:
            _temp_sessions[temp_session_id] = (SessionContainer(session_id=temp_session_id, user_id="TEMP"), now_ts)
        container, _ = _temp_sessions[temp_session_id]
        _temp_sessions[temp_session_id] = (container, now_ts)  # 접근 시마다 TTL 갱신

        # 시나리오4: @PLAN 또는 기존 일정이 있으면 Core.run(Router) 사용
        use_pipeline = bool(_re.match(r'^@PLAN', message, _re.IGNORECASE))
        content = _re.sub(r'^@PLAN\s*', '', message, flags=_re.IGNORECASE).strip() if use_pipeline else message

        async def _stream():
            if use_pipeline or container.widget_state.get("t_pn"):
                from ...router.core import Core
                bot_text, new_widgets = await Core.run(
                    current=content,
                    use_pipeline=use_pipeline,
                    **container.router_context(),
                )
                new_widgets.pop("_sl_ctx", None)
                await container.commit_turn(user_text=content, bot_text=bot_text, widget_state=new_widgets)
            else:
                bot_text = await container.process_user_input(content)
            for char in bot_text:
                yield char
                await asyncio.sleep(0.03)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def get_temp_trip_plan(temp_session_id: str) -> dict:
        """임시 세션 여행 일정 반환 (프론트 포맷)."""
        entry = _temp_sessions.get(temp_session_id)
        if not entry:
            return {"plan": []}
        container, _ = entry
        from ..widget.widget_trip_plan import TripPlanWidget
        t_pn_raw = container.widget_state.get("t_pn", [])
        if not t_pn_raw:
            return {"plan": []}
        widget = TripPlanWidget()
        widget.set_for_llm(t_pn_raw)
        return {"plan": widget.get_for_front()}

    @staticmethod
    async def get_temp_trip_range(temp_session_id: str) -> dict:
        """임시 세션 달력 범위 반환."""
        entry = _temp_sessions.get(temp_session_id)
        if not entry:
            return {"ranges": [], "selected_date": None}
        container, _ = entry
        return {"ranges": container.widget_state.get("t_cd", []), "selected_date": None}

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
    async def share_chat(session_id: str, user_id: str, redis: Any) -> dict[str, str | bool]:
        import secrets
        from ...memory.constants import USER_ANALYSIS_TTL  # 7일 재사용
        from ...memory.cacher import Cacher
        token = secrets.token_urlsafe(24)
        await redis.set_str(f"share:{token}", session_id, USER_ANALYSIS_TTL)
        # 시나리오9: 공유 시점의 위젯 상태(달력·일정)도 함께 저장
        try:
            from ..widget.widget_trip_plan import TripPlanWidget as _TW
            trip_id = await redis.get_str(f"session:{session_id}:trip_id")
            ws = await Cacher.get_session_widgets(session_id, redis, trip_id)
            if ws:
                # t_pn은 Redis에 2D 행렬(LLM 내부 형식)로 저장됨.
                # 프론트 renderPlan은 [{day, date, items:[...]}] 형식을 요구하므로 변환.
                tw = _TW()
                tw.set_for_llm(ws.get("t_pn", []))
                snap = {
                    "t_cd": ws.get("t_cd", []),
                    "t_pn": tw.get_for_front(),
                    "t_mk": ws.get("t_mk", []),
                }
                await redis.set_str(f"share:{token}:widgets", json.dumps(snap, ensure_ascii=False), USER_ANALYSIS_TTL)
        except Exception:
            pass
        return {"success": True, "share_url": f"/#/shared/{token}"}

    @staticmethod
    async def _get_container(session_id: str, user_id: str, redis: Any, manager: Any = None) -> SessionContainer:
        """세션 컨테이너 초기화 게이트.
        trip_id가 Redis에 없으면 SessionOpenEvent로 trip_id 캐시 + plan hydrate를 보장한 뒤 로드.
        """
        if not await redis.get_str(f"session:{session_id}:trip_id") and manager is not None:
            from ...memory.events import SessionOpenEvent
            await manager.emit_and_wait(SessionOpenEvent(session_id=session_id, user_id=user_id))
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

        # 전각 @(＠, U+FF20)를 일반 @로 정규화
        message = message.replace('＠', '@')

        # @SEARCH 는 PPL-only (SDB/DDB/LLM 없음)
        if _re.match(r'^@SEARCH\s+', message, _re.IGNORECASE):
            query = _re.sub(r'^@SEARCH\s+', '', message, flags=_re.IGNORECASE).strip()
            return await ChatService._ppl_search_response(session_id, query, user_id, redis, manager)

        # @WEATHER — DDB 날씨 조회 (LLM 없음)
        if _re.match(r'^@WEATHER\b', message, _re.IGNORECASE):
            query = _re.sub(r'^@WEATHER\s*', '', message, flags=_re.IGNORECASE).strip()
            return await ChatService._weather_response(session_id, query, user_id, redis, manager)

        # @PLAN만 여행 일정 파이프라인(ROUTER). 그 외 일반 대화는 simple 응답.
        # (여행 JSON 라우터는 '넌 누구니?' 같은 일반 질문도 여행 얘기로 답하므로 분기)
        if not is_team:
            content = _re.sub(r'^@BOT\s+', '', message, flags=_re.IGNORECASE).strip()
            use_pipeline = bool(_re.match(r'^@PLAN', content, _re.IGNORECASE))
            content = _re.sub(r'^@PLAN\s*', '', content, flags=_re.IGNORECASE).strip()
            if use_pipeline:
                return await ChatService._stream_bot_response(session_id, content, user_id, redis, manager, use_pipeline=True)
            return await ChatService._stream_simple_bot_response(session_id, content, user_id, redis, manager)

        # 팀 세션: @BOT/@PLAN로 시작할 때만 AI가 응답. 일반 팀 채팅엔 끼어들지 않음.
        if _re.match(r'^@(BOT|PLAN)\b', message.strip(), _re.IGNORECASE):
            content = _re.sub(r'^@BOT\s+', '', message.strip(), flags=_re.IGNORECASE).strip()
            use_pipeline = bool(_re.match(r'^@PLAN', content, _re.IGNORECASE))
            content = _re.sub(r'^@PLAN\s*', '', content, flags=_re.IGNORECASE).strip()
            if use_pipeline:
                return await ChatService._stream_bot_response(session_id, content, user_id, redis, manager, use_pipeline=True)
            return await ChatService._stream_simple_bot_response(session_id, content, user_id, redis, manager)

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
            container = await ChatService._get_container(session_id, user_id, redis, manager)
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
    async def _ppl_search_response(session_id: str, query: str, triggering_user_id: str, redis: Any, manager: Any) -> StreamingResponse:
        """@SEARCH — PPL(Perplexity)만 실행, LLM 없음."""
        async def _stream():
            bot_text = "검색 결과를 가져올 수 없습니다."
            try:
                from ...router.protocol import QUST
                from ...kernel.ppl import PPL
                container = await ChatService._get_container(session_id, triggering_user_id, redis, manager)
                ws = container.widget_state
                qust = QUST(
                    CC=query,
                    SSN_TPC=container.session_topic or "",
                    T_CD=ws.get("t_cd") or [],
                    # T_MK/T_PN은 typed 객체가 필요해 raw dict를 넘기면 AttributeError 발생
                    # @SEARCH 검색 컨텍스트에는 CC + T_CD + SSN_TPC면 충분
                    T_MK=[],
                    T_PN=[],
                )
                qust = await PPL(search_mode=True).run(qust)
                bot_text = qust.PPL or "검색 결과가 없습니다."
                await container.commit_turn(user_text=query, bot_text=bot_text, widget_state=ws)
                await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
            except Exception as e:
                print(f"[PPL Search] 오류: {e}", flush=True)

            bot_now    = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id":   bot_msg_id,
                "session_id":   session_id,
                "sender_id":    None,
                "sender_name":  "AI",
                "sender_type":  "ai",
                "message_type": "text",
                "content":      bot_text,
                "created_at":   bot_now.isoformat(),
            }, redis, manager)
            NotifyService.push_to_session(session_id, json.dumps({
                "type":        "message",
                "sender_id":   "bot",
                "sender_name": "AI",
                "content":     bot_text,
                "msg_id":      bot_msg_id,
                "ts":          bot_now.isoformat(),
            }, ensure_ascii=False), exclude_user=triggering_user_id)

            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def _weather_response(session_id: str, query: str, triggering_user_id: str, redis: Any, manager: Any) -> StreamingResponse:
        """@WEATHER — DDB 날씨 조회, LLM 없음."""
        async def _stream():
            bot_text = "날씨 정보를 가져올 수 없습니다."
            try:
                from ...router.protocol import QUST
                from ...kernel.ddb import DDB
                from ...kernel.db_connector import DBConnector
                from ...execute_unit.widget.widget_trip_clander import TripClanderWidget

                container = await ChatService._get_container(session_id, triggering_user_id, redis, manager)
                ws = container.widget_state

                t_cd = ws.get("t_cd") or []
                if not t_cd and query:
                    t_cd = TripClanderWidget._normalize_dates(query) or []

                qust = QUST(CC=query, SSN_TPC=container.session_topic or "", T_CD=t_cd, T_MK=[], T_PN=[])
                connector = DBConnector()
                try:
                    qust = await DDB(connector).run(qust)
                finally:
                    connector.close()

                if qust.dDB:
                    raw_text = _format_weather_raw(qust.dDB)
                    bot_text = await _summarize_weather_with_llm(raw_text)
                    await _save_weather_snapshot(session_id, triggering_user_id, t_cd, container.session_topic or "", qust.dDB, redis)
                else:
                    bot_text = "해당 날짜의 날씨 정보가 없습니다. 여행 날짜(달력)를 먼저 설정해주세요."

                user_label = f"@weather {query}".strip() if query else "@weather"
                await container.commit_turn(user_text=user_label, bot_text=bot_text, widget_state=ws)
                await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
            except Exception as e:
                print(f"[WeatherService] 오류: {e}", flush=True)

            bot_now    = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id":   bot_msg_id,
                "session_id":   session_id,
                "sender_id":    None,
                "sender_name":  "AI",
                "sender_type":  "ai",
                "message_type": "text",
                "content":      bot_text,
                "created_at":   bot_now.isoformat(),
            }, redis, manager)
            NotifyService.push_to_session(session_id, json.dumps({
                "type":        "message",
                "sender_id":   "bot",
                "sender_name": "AI",
                "content":     bot_text,
                "msg_id":      bot_msg_id,
                "ts":          bot_now.isoformat(),
            }, ensure_ascii=False), exclude_user=triggering_user_id)

            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def _stream_bot_response(session_id: str, query: str, triggering_user_id: str, redis: Any, manager: Any, use_pipeline: bool = False) -> StreamingResponse:

        async def _stream():
            bot_text = "죄송합니다, 응답을 생성할 수 없습니다."
            try:
                from ...memory.constants import SL_CTX_TTL, PENDING_TTL
                from ...router.core import Core
                container = await ChatService._get_container(session_id, triggering_user_id, redis, manager)
                effective_query = query
                if container.trip_id:
                    reset_msg = await redis.get_str(f"trip:{container.trip_id}:reset_pending_msg")
                    if reset_msg:
                        await redis.delete(f"trip:{container.trip_id}:reset_pending_msg")
                        effective_query = f"[시스템: {reset_msg}]\n{query}"
                kw_bag = await Cacher.get_kw_bag(container.trip_id, redis) if container.trip_id else {}
                bot_text, new_widgets = await Core.run(
                    current=effective_query,
                    user_id=triggering_user_id,
                    kw_bag=kw_bag,
                    use_pipeline=use_pipeline,
                    **container.router_context(),
                )

                sl_ctx = new_widgets.pop("_sl_ctx", {})
                t_sl   = new_widgets.get("t_sl", "")

                if t_sl and sl_ctx:
                    # CC를 sl_ctx에 보존 → A 선택 시 꺼내서 봇 메시지로 전송
                    sl_ctx["_cc"] = bot_text
                    pending = {
                        "t_cd": new_widgets.get("t_cd", []),
                        "t_mp": new_widgets.get("t_mp", []),
                        "t_mk": new_widgets.get("t_mk", []),
                    }
                    await Cacher.save_pending_widgets(session_id, pending, redis, PENDING_TTL)
                    await Cacher.save_sl_ctx(session_id, sl_ctx, redis, SL_CTX_TTL)
                    prev = container.widget_state
                    new_widgets["t_cd"] = prev.get("t_cd", [])
                    new_widgets["t_mp"] = prev.get("t_mp", [])
                    new_widgets["t_mk"] = prev.get("t_mk", [])
                    new_widgets["t_pn"] = prev.get("t_pn", [])  # 선택 전까진 이전 상태 유지
                    # 세션 컨텍스트에는 bot_text 기록 (LLM 맥락 유지), 화면 출력은 하지 않음
                    await container.commit_turn(user_text=query, bot_text=bot_text, widget_state=new_widgets)
                    await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
                    # trip-select 위젯 표시 트리거 (CC는 출력하지 않음)
                    NotifyService.push_to_session(session_id, json.dumps({
                        "type": "widget_update",
                        "session_id": session_id,
                        "widgets": {"t_sl": t_sl},
                    }, ensure_ascii=False))
                    return  # CC 스트리밍 없음, 메시지 저장 없음
                else:
                    prev = container.widget_state
                    for key in ("t_pn", "t_cd", "t_mp", "t_mk"):
                        if not new_widgets.get(key) and prev.get(key):
                            new_widgets[key] = prev[key]
                    # @BOT/@SEARCH 모드: T_PN은 수동 편집 내용 보존 — LLM 출력 무시
                    if not use_pipeline:
                        new_widgets["t_pn"] = prev.get("t_pn", [])
                    await container.commit_turn(user_text=query, bot_text=bot_text, widget_state=new_widgets)
                    await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
                    _notify = {}
                    if use_pipeline and new_widgets.get("t_pn"):
                        _notify["t_pn"] = new_widgets["t_pn"]
                    if new_widgets.get("t_cd") and new_widgets.get("t_cd") != prev.get("t_cd"):
                        _notify["t_cd"] = new_widgets["t_cd"]
                    if _notify:
                        NotifyService.push_to_session(session_id, json.dumps({
                            "type": "widget_update",
                            "session_id": session_id,
                            "widgets": _notify,
                        }, ensure_ascii=False))
            except Exception as e:
                print(f"[ChatService._stream_bot_response] {session_id} 오류: {e}")

            # T_SL 게이트 활성 시 위에서 return됨 → 아래는 일반 응답 전용
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
            await _maybe_notify_response_complete(session_id, triggering_user_id, redis, manager)

            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def _stream_simple_bot_response(session_id: str, query: str, triggering_user_id: str, redis: Any, manager: Any) -> StreamingResponse:
        """@PLAN 없는 일반 대화 — GENERATION_PROMPT 기반 단순 LLM 응답."""

        async def _stream():
            bot_text = "죄송합니다, 응답을 생성할 수 없습니다."
            try:
                container = await ChatService._get_container(session_id, triggering_user_id, redis, manager)
                bot_text = await container.process_user_input(query)
                await ChatService._apply_title_change(container, session_id, triggering_user_id, redis, manager)
            except Exception as e:
                print(f"[ChatService._stream_simple_bot_response] {session_id} 오류: {e}")

            bot_now    = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id": bot_msg_id,
                "session_id": session_id,
                "sender_id":  None,
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
            await _maybe_notify_response_complete(session_id, triggering_user_id, redis, manager)

            for char in bot_text:
                yield char.encode()
                await asyncio.sleep(0.02)

        return StreamingResponse(_stream(), media_type="text/plain")

    @staticmethod
    async def select_route(session_id: str, user_id: str, choice: str, redis: Any, manager: Any) -> dict:
        """T_SL 선택지 처리.
        A 선택: 조용히 적용 (CC가 이미 A안을 설명함).
        B 선택: T_SL 텍스트를 봇 메시지로 전송 후 적용.
        선택 버블은 양쪽 다 표시하지 않는다.
        """
        from ...kernel.keyword_scorer import apply_selection
        from ...memory.constants import PENDING_TTL, SL_CTX_TTL, KW_BAG_TTL
        from ..widget import WidgetUnit

        sl_ctx = await Cacher.get_sl_ctx(session_id, redis)
        if not sl_ctx:
            raise ValueError("sl_ctx_not_found")

        # A: sl_ctx["_cc"]에서 CC 꺼냄 / B: T_SL Redis에서 읽음 (commit_turn 이전)
        reveal_text = ""
        if choice == 'A':
            reveal_text = sl_ctx.get("_cc", "")
        else:
            reveal_text = await WidgetUnit.get_t_sl(session_id, redis)

        container = await ChatService._get_container(session_id, user_id, redis, manager)
        if container.trip_id:
            bag = await Cacher.get_kw_bag(container.trip_id, redis)
            new_bag = apply_selection(choice, sl_ctx, bag)
            await Cacher.save_kw_bag(container.trip_id, new_bag, redis, KW_BAG_TTL, manager)
        await Cacher.save_sl_ctx(session_id, {}, redis, SL_CTX_TTL)

        pending = await Cacher.get_pending_widgets(session_id, redis)
        merged = dict(container.widget_state)
        merged.update(pending)
        merged["t_sl"] = ""
        chosen_t_pn = sl_ctx.get(choice, {}).get("t_pn")
        if chosen_t_pn:
            merged["t_pn"] = chosen_t_pn
        merged.pop("_sl_ctx", None)
        await container.commit_turn(widget_state=merged)
        await Cacher.save_pending_widgets(session_id, {}, redis, 1)

        # A/B 선택: 해당 안의 텍스트를 봇 메시지로 전송
        if reveal_text:
            bot_now = datetime.now(tz=timezone.utc)
            bot_msg_id = "msg_" + str(uuid.uuid4())[:12]
            await Cacher.save_message(session_id, {
                "message_id":   bot_msg_id,
                "session_id":   session_id,
                "sender_id":    "bot",
                "sender_name":  "AI",
                "sender_type":  "bot",
                "message_type": "chat",
                "content":      reveal_text,
                "created_at":   bot_now.isoformat(),
            }, redis, manager)
            NotifyService.push_to_session(session_id, json.dumps({
                "type":        "message",
                "sender_id":   "bot",
                "sender_name": "AI",
                "content":     reveal_text,
                "msg_id":      bot_msg_id,
                "msg_type":    "chat",
                "ts":          bot_now.isoformat(),
            }, ensure_ascii=False))

        NotifyService.push_to_session(session_id, json.dumps({
            "type": "widget_update",
            "session_id": session_id,
            "widgets": {
                "t_sl": "",
                "t_cd": merged.get("t_cd", []),
                "t_mp": merged.get("t_mp", []),
                "t_mk": merged.get("t_mk", []),
                "t_pn": merged.get("t_pn", []),
            },
        }, ensure_ascii=False))
        return {"success": True, "choice": choice}

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
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        up_dir = os.path.join(base, "uploads", session_id, user_id)
        os.makedirs(up_dir, exist_ok=True)

        names = []
        originals = []
        for file in files:
            content = await file.read()
            if len(content) > _MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"파일 크기는 20MB를 초과할 수 없습니다: {file.filename}")
            content_type = (file.content_type or "").split(";")[0].strip()
            if not content_type or content_type not in _ALLOWED_MIME_TYPES:
                # 클립보드 붙여넣기 시 MIME이 비거나 octet-stream일 수 있음 → 확장자로 추론
                _ext_fallback = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
                content_type = _EXT_TO_MIME.get(_ext_fallback, content_type)
            if content_type not in _ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=415, detail=f"허용되지 않는 파일 형식입니다: {file.filename}")
            original = os.path.basename(file.filename or "upload")
            ext = os.path.splitext(original)[1].lower()
            safe_name = uuid.uuid4().hex[:12] + ext
            dest = os.path.join(up_dir, safe_name)
            with open(dest, "wb") as f:
                f.write(content)
            names.append(safe_name)
            originals.append(original)

        if names:
            await ChatService._save_file_message(session_id, user_id, names, originals, redis, manager)
            participants = await Cacher.get_session_participants(session_id, redis, manager)
            is_team = any(p.get("user_id") != user_id and p.get("user_id") != "bot" for p in participants)
            if not is_team:
                _spawn_task(ChatService._respond_to_images(session_id, user_id, up_dir, names, redis, manager))
        return {"success": True, "uploaded_files": originals}

    @staticmethod
    async def _save_file_message(session_id: str, user_id: str, safe_names: list[str], original_names: list[str], redis: Any, manager: Any) -> None:
        from ...memory.events import SaveFileRecordsEvent
        profile = await Cacher.get_user_profile(user_id, redis, manager)
        sender_name = (profile.get("nickname") or "").strip() or "사용자"
        now = datetime.now(tz=timezone.utc)
        msg_id = "msg_" + str(uuid.uuid4())[:12]
        content = f"[파일 첨부] {', '.join(original_names)}"

        await Cacher.save_message(session_id, {
            "message_id": msg_id,
            "session_id": session_id,
            "sender_id": user_id,
            "sender_name": sender_name,
            "sender_type": "user",
            "message_type": "file",
            "content": content,
            "created_at": now.isoformat(),
            "files": safe_names,
        }, redis, manager)

        if manager is not None:
            manager.emit(SaveFileRecordsEvent(
                session_id=session_id,
                message_id=msg_id,
                uploader_id=user_id,
                safe_names=safe_names,
                original_names=original_names,
            ))

        NotifyService.push_to_session(session_id, json.dumps({
            "type": "message",
            "sender_id": user_id,
            "sender_name": sender_name,
            "content": content,
            "msg_id": msg_id,
            "ts": now.isoformat(),
            "msg_type": "file",
            "files": safe_names,
        }, ensure_ascii=False))

    @staticmethod
    async def _respond_to_images(session_id: str, user_id: str, up_dir: str, safe_names: list[str], redis: Any, manager: Any) -> None:
        """개인 세션에서 이미지 업로드 시 봇이 이미지를 보고 응답."""
        from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY
        from ...kernel.llm import LLM

        images: list[tuple[str, str]] = []
        for safe_name in safe_names:
            img_path = os.path.join(up_dir, safe_name)
            ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "jpg"
            mime = _EXT_TO_MIME.get(ext, "image/jpeg")
            try:
                payload = await asyncio.to_thread(_read_image_payload, img_path, mime)
                images.append(payload)
            except Exception as e:
                print(f"[ChatService._respond_to_images] 이미지 읽기 실패 {safe_name}: {e}")

        if not images:
            return

        prompt = "업로드된 이미지를 설명해줘." if len(images) == 1 else f"업로드된 이미지 {len(images)}장을 설명해줘."
        try:
            bot_text = await LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY).ask(prompt, images=images)
        except Exception as e:
            print(f"[ChatService._respond_to_images] LLM 호출 실패: {e}")
            return

        bot_now = datetime.now(tz=timezone.utc)
        bot_msg_id = "msg_" + uuid.uuid4().hex[:12]
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
        }, ensure_ascii=False))

        # 이미지 분석 내용을 SSN_PCL(과거 대화)에 저장
        try:
            container = await ChatService._get_container(session_id, user_id, redis, manager)
            img_label = ", ".join(safe_names)
            await container.commit_turn(
                user_text=f"[이미지 첨부: {img_label}]",
                bot_text=bot_text,
            )
        except Exception as _hist_e:
            print(f"[ChatService._respond_to_images] 대화 이력 저장 실패: {_hist_e}")
