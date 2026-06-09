"""
[역할] PostgreSQL과 직접 통신하는 유일한 계층.
       Loader는 EventHandler(manager)에 의해서만 호출되며 Redis ↔ PG 동기화를 담당한다.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from psycopg2.extras import Json as PgJson
from fastapi import FastAPI, HTTPException


class Loader:

    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """PostgreSQL + Redis 초기화 → app.state 주입 → 종료 시 정리."""
        from .adapters import PgAdapter, RedisAdapter
        from .event_handler import EventHandler

        pg_adapter = PgAdapter(os.environ["DATABASE_URL"])
        redis_adapter = RedisAdapter(os.environ["REDIS_URL"])

        manager = EventHandler()
        await manager.start(pg_adapter, redis_adapter)

        app.state.postgres = pg_adapter
        app.state.redis = redis_adapter
        app.state.manager = manager

        print("[Loader] PostgreSQL & Redis 초기화 완료")
        _weather_task = asyncio.create_task(_weather_change_loop(pg_adapter, redis_adapter))
        try:
            yield
        finally:
            _weather_task.cancel()
            await manager.stop()
            await redis_adapter.close()
            pg_adapter.close()
            print("[Loader] 앱 종료 완료")

    @staticmethod
    async def kakao_oauth_lookup_or_create(
        postgres: Any,
        *,
        provider_uid: str,
        nickname: str,
        email: Optional[str],
        profile_img_url: str,
        state: Optional[str],
        redis: Any,
    ) -> dict[str, Any]:
        """카카오 OAuth 사용자 조회/생성/연동 처리."""
        now = datetime.now(tz=timezone.utc)

        if state:
            link_key = f"kakao_link:{state}"
            link_user_id = await redis.get_str(link_key)
            if link_user_id:
                await redis.delete(link_key)
                if await postgres.read("UserOAuth", {"provider": "kakao", "provider_uid": provider_uid}):
                    raise HTTPException(status_code=409, detail="이미 다른 계정에 연동된 카카오 계정입니다")
                try:
                    await postgres.create("UserOAuth", {
                        "oauth_id": "oauth_" + str(uuid.uuid4())[:16],
                        "user_id": link_user_id,
                        "provider": "kakao",
                        "provider_uid": provider_uid,
                        "created_at": now,
                    })
                except RuntimeError as e:
                    raise HTTPException(status_code=500, detail=f"카카오 계정 연동 실패: {e}")
                return {"linked": True, "user_id": link_user_id}

        oauth_rows = await postgres.read("UserOAuth", {"provider": "kakao", "provider_uid": provider_uid})
        if oauth_rows:
            return {
                "user_id": oauth_rows[0]["user_id"],
                "is_new": False,
                "nickname": nickname,
                "email": email,
            }

        user_id = "KKO:" + str(uuid.uuid4())[:16]
        try:
            await postgres.create("User", {"user_id": user_id, "user_type": "KKO", "status": "active", "created_at": now})
            await postgres.create("UserOAuth", {
                "oauth_id": "oauth_" + str(uuid.uuid4())[:16],
                "user_id": user_id,
                "provider": "kakao",
                "provider_uid": provider_uid,
                "created_at": now,
            })
            await postgres.create("UserProfile", {
                "user_id": user_id,
                "email": email,
                "nickname": nickname,
                "profile_img_url": profile_img_url,
                "updated_at": now,
            })
            await postgres.create("UserPreferences", {"user_id": user_id, "updated_at": now})
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"KKO 계정 생성 실패: {e}")

        await Loader.ensure_personal_team(postgres, user_id)
        return {"user_id": user_id, "is_new": True, "nickname": nickname, "email": email}

    @staticmethod
    async def signup(postgres: Any, data: dict[str, Any]) -> dict[str, Any]:
        email = data.get("email", "").strip()
        password = data.get("password", "")
        nickname = data.get("nickname", "").strip()
        if not email or not password:
            raise HTTPException(status_code=400, detail="이메일과 비밀번호는 필수입니다")

        if await postgres.read("UserProfile", {"email": email}):
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다")

        user_id = "MEM:" + str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        pw_hash = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")

        try:
            await postgres.create("User", {"user_id": user_id, "user_type": "MEM", "status": "active", "created_at": now})
            await postgres.create("UserProfile", {"user_id": user_id, "email": email, "nickname": nickname, "updated_at": now})
            await postgres.create("UserSecurity", {"user_id": user_id, "password_hash": pw_hash, "login_fail_count": 0})
            await postgres.create("UserPreferences", {"user_id": user_id, "updated_at": now})
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=f"회원가입 실패: {e}")

        await Loader.ensure_personal_team(postgres, user_id)
        return {"user_id": user_id, "status": "success"}

    @staticmethod
    async def login(postgres: Any, redis: Any, email: str, password: str) -> dict[str, Any]:
        from ..jwt_utils import create_access_token, create_refresh_token, REFRESH_TOKEN_EXPIRE_DAYS as _EXP_DAYS
        _ttl = _EXP_DAYS * 24 * 3600

        rows = await postgres.query(
            "SELECT up.user_id, up.nickname, u.user_type, u.status FROM user_profile up JOIN users u ON up.user_id = u.user_id WHERE up.email = :email LIMIT 1",
            {"email": email},
        )
        if not rows:
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
        row = rows[0]
        user_id = row["user_id"]
        if row.get("status") == "deleted":
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
        if row["user_type"] != "MEM":
            raise HTTPException(status_code=400, detail="SNS 연동 계정입니다. 카카오 로그인을 이용해주세요")

        sec_rows = await postgres.read("UserSecurity", {"user_id": user_id})
        if not sec_rows:
            raise HTTPException(status_code=500, detail="보안 정보 조회 실패")

        sec = sec_rows[0]
        now = datetime.now(tz=timezone.utc)
        if sec.get("locked_until"):
            locked_until = sec["locked_until"]
            if isinstance(locked_until, str):
                locked_until = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
            if locked_until > now:
                raise HTTPException(status_code=403, detail="계정이 잠겨 있습니다. 잠시 후 다시 시도하세요")

        if not bcrypt.checkpw(password.encode("utf-8")[:72], sec["password_hash"].encode("utf-8")):
            fail_count = sec.get("login_fail_count", 0) + 1
            update_data: dict[str, Any] = {"login_fail_count": fail_count}
            if fail_count >= 5:
                update_data["locked_until"] = now + timedelta(minutes=30)
            await postgres.update("UserSecurity", {"user_id": user_id}, update_data)
            detail = "로그인 5회 실패. 계정이 30분간 잠겼습니다" if fail_count >= 5 else "이메일 또는 비밀번호가 올바르지 않습니다"
            raise HTTPException(status_code=403 if fail_count >= 5 else 401, detail=detail)

        await postgres.update("UserSecurity", {"user_id": user_id}, {"last_login_at": now, "login_fail_count": 0})
        # 단일 기기 정책: 기존 refresh 토큰 전부 폐기 + last_login_at 갱신
        existing = await redis.execute({"action": "smembers", "key": f"user:{user_id}:refresh_jtis"})
        had_active_session = bool(existing.get("data"))
        await Loader.logout_all_devices(redis, user_id)
        login_ts = int(now.timestamp())
        await redis.set_str(f"user:{user_id}:last_login_at", str(login_ts), _ttl)
        access_token = create_access_token(user_id)
        refresh_token, jti = create_refresh_token(user_id)
        await redis.set_str(f"auth:refresh:{jti}", user_id, _ttl)
        await redis.execute({
            "action": "sadd",
            "key": f"user:{user_id}:refresh_jtis",
            "member": jti,
        })
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id,
            "type": "MEM",
            "nickname": row.get("nickname", ""),
            "email": email,
            "status": "success",
            "had_active_session": had_active_session,
        }

    @staticmethod
    async def refresh_token(redis: Any, refresh_token: str) -> dict[str, Any]:
        from ..jwt_utils import create_access_token, verify_refresh_token

        payload = verify_refresh_token(refresh_token)
        if not await redis.get_str(f"auth:refresh:{payload['jti']}"):
            raise HTTPException(status_code=401, detail="만료되었거나 로그아웃된 토큰입니다")
        return {"access_token": create_access_token(payload["sub"]), "status": "success"}

    @staticmethod
    async def logout(postgres: Any, redis: Any, refresh_token: str, user_id: Optional[str] = None) -> None:
        """토큰 폐기만. flush는 manager가 선행 처리한다."""
        from ..jwt_utils import verify_refresh_token

        try:
            payload = verify_refresh_token(refresh_token)
            if jti := payload.get("jti"):
                await redis.delete(f"auth:refresh:{jti}")
        except HTTPException:
            pass

    @staticmethod
    async def get_my_info(postgres: Any, user_id: str) -> dict[str, Any]:
        rows = await postgres.read("UserProfile", {"user_id": user_id})
        if rows:
            p = rows[0]
            return {
                "status": "success",
                "user_id": user_id,
                "user_type": user_id.split(":")[0],
                "nickname": p.get("nickname", ""),
                "email": p.get("email", ""),
            }
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다")

    @staticmethod
    async def get_settings(postgres: Any, user_id: str) -> dict[str, Any]:
        rows = await postgres.query(
            """SELECT up.bio, up.nickname, up.email, up.extra_contacts,
                      upr.ui_settings, upr.style, upr.travel, upr.analysis,
                      uo.provider AS oauth_provider
               FROM user_profile up
               LEFT JOIN user_preferences upr ON upr.user_id = up.user_id
               LEFT JOIN user_oauth uo ON uo.user_id = up.user_id
               WHERE up.user_id = :uid LIMIT 1""",
            {"uid": user_id},
        )
        if not rows:
            return {"status": "success", "data": {}, "profile": {}, "style": {}, "travel": {}}
        row = rows[0]
        return {
            "status": "success",
            "data": row.get("ui_settings") or {},
            "profile": {
                "bio": row.get("bio"),
                "nickname": row.get("nickname"),
                "email1": row.get("email"),
                "extra_contacts": row.get("extra_contacts") or [],
            },
            "style": row.get("style") or {},
            "travel": row.get("travel") or {},
            "analysis": row.get("analysis") or "",
            "oauth_provider": row.get("oauth_provider"),
        }

    @staticmethod
    async def ensure_personal_team(postgres: Any, user_id: str) -> str:
        rows = await postgres.query(
            "SELECT t.team_id FROM teams t JOIN team_members tm ON t.team_id = tm.team_id WHERE tm.user_id = :user_id AND tm.role = 'owner' LIMIT 1",
            {"user_id": user_id},
        )
        if rows:
            return rows[0]["team_id"]

        team_id = "team_" + str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc)
        await postgres.create("Team", {"team_id": team_id, "created_by": user_id, "name": "내 팀", "created_at": now})
        await postgres.create("TeamMember", {"team_id": team_id, "user_id": user_id, "role": "owner", "joined_at": now})
        return team_id

    @staticmethod
    async def ensure_misc_trip(postgres: Any, user_id: str) -> str:
        team_id = await Loader.ensure_personal_team(postgres, user_id)
        rows = await postgres.query(
            "SELECT trip_id FROM trips WHERE team_id = :team_id AND is_misc = true LIMIT 1",
            {"team_id": team_id},
        )
        if rows:
            return rows[0]["trip_id"]

        trip_id = "trip_" + str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc)
        await postgres.create("Trip", {
            "trip_id": trip_id,
            "team_id": team_id,
            "created_by": user_id,
            "title": "기타",
            "is_misc": True,
            "status": "planning",
            "created_at": now,
            "updated_at": now,
        })
        return trip_id

    @staticmethod
    async def get_trip_list(postgres: Any, user_id: str) -> list[dict[str, Any]]:
        return await postgres.query(
            """SELECT tr.trip_id, tr.title, tr.color, tr.destination,
                      tr.start_date, tr.end_date, tr.status, tr.is_misc,
                      tr.team_id, tr.created_by, tr.created_at
               FROM trips tr JOIN team_members tm ON tr.team_id = tm.team_id
               WHERE tm.user_id = :user_id AND tr.status != 'deleted'
               ORDER BY tr.is_misc ASC, tr.created_at DESC""",
            {"user_id": user_id},
        )

    @staticmethod
    async def create_trip(postgres: Any, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        team_id = await Loader.ensure_personal_team(postgres, user_id)
        trip_id = "trip_" + str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc)
        await postgres.create("Trip", {
            "trip_id": trip_id,
            "team_id": team_id,
            "created_by": user_id,
            "title": data.get("title", "새 여행"),
            "color": data.get("color"),
            "destination": data.get("destination"),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "status": "planning",
            "created_at": now,
            "updated_at": now,
        })
        return {"trip_id": trip_id, "title": data.get("title", "새 여행"), "color": data.get("color"), "team_id": team_id}

    @staticmethod
    async def update_trip(postgres: Any, trip_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        update_data: dict[str, Any] = {"updated_at": datetime.now(tz=timezone.utc)}
        for field in ("title", "color", "destination", "start_date", "end_date", "status"):
            if field in data:
                update_data[field] = data[field]
        await postgres.update("Trip", {"trip_id": trip_id}, update_data)
        return {"success": True, "trip_id": trip_id}

    @staticmethod
    async def delete_trip(postgres: Any, trip_id: str, user_id: str) -> dict[str, Any]:
        misc_trip_id = await Loader.ensure_misc_trip(postgres, user_id)
        now = datetime.now(tz=timezone.utc)
        await postgres.query(
            "UPDATE sessions SET trip_id = :misc_id, updated_at = :now WHERE trip_id = :trip_id AND is_active = true",
            {"misc_id": misc_trip_id, "trip_id": trip_id, "now": now},
        )
        await postgres.update("Trip", {"trip_id": trip_id, "created_by": user_id}, {"status": "deleted", "updated_at": now})
        return {"success": True}

    @staticmethod
    async def get_session_list(postgres: Any, user_id: str, trip_id: Optional[str] = None) -> list[dict[str, Any]]:
        trip_filter = ""
        params: dict[str, Any] = {"user_id": user_id}
        if trip_id == "misc":
            trip_filter = "AND tr.is_misc = true"
        elif trip_id:
            trip_filter = "AND s.trip_id = :trip_id"
            params["trip_id"] = trip_id

        return await postgres.query(
            f"""SELECT s.session_id, s.title, s.topic, s.color,
                       s.trip_id, s.is_manual_title, s.created_at, s.updated_at,
                       tr.color AS trip_color, tr.title AS trip_title, tr.is_misc AS trip_is_misc,
                       sp_me.role AS user_role,
                       (SELECT COUNT(*) - 1 FROM session_participants sp2 WHERE sp2.session_id = s.session_id) AS participant_count,
                       (SELECT COUNT(*) FROM conversations c
                        WHERE c.session_id = s.session_id
                          AND c.sender_id != :user_id
                          AND (sp_me.last_read_at IS NULL OR c.created_at > sp_me.last_read_at)) AS unread_count
                FROM sessions s
                JOIN session_participants sp_me ON sp_me.session_id = s.session_id AND sp_me.user_id = :user_id
                LEFT JOIN trips tr ON s.trip_id = tr.trip_id
                WHERE s.is_active = true {trip_filter}
                ORDER BY s.updated_at DESC""",
            params,
        )

    @staticmethod
    async def create_session_record(postgres: Any, session_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc)
        title = data.get("title", "새 세션")
        await postgres.create("Session", {
            "session_id": session_id,
            "trip_id": data.get("trip_id"),
            "created_by": user_id,
            "title": title,
            "is_manual_title": False,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        })
        await postgres.create("SessionParticipant", {
            "session_id": session_id, "user_id": user_id, "role": "master", "joined_at": now, "last_read_at": now,
        })
        await postgres.query(
            "INSERT INTO session_participants (session_id, user_id, role, joined_at) VALUES (:sid, 'bot', 'bot', :now) ON CONFLICT (session_id, user_id) DO NOTHING",
            {"sid": session_id, "now": now},
        )
        return {"session_id": session_id, "title": title}

    @staticmethod
    async def update_session_record(postgres: Any, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
        update_data: dict[str, Any] = {"updated_at": datetime.now(tz=timezone.utc)}
        for field in ("title", "is_manual_title", "topic", "context_summary", "trip_id", "is_active", "color"):
            if field in data:
                update_data[field] = data[field]
        await postgres.update("Session", {"session_id": session_id}, update_data)
        return {"success": True}

    @staticmethod
    async def leave_session(postgres: Any, session_id: str, user_id: str) -> dict[str, Any]:
        rows = await postgres.query(
            "SELECT role FROM session_participants WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )
        if not rows:
            return {"success": True}
        if rows[0]["role"] == "master":
            raise HTTPException(status_code=403, detail="마스터는 직접 나갈 수 없습니다. 세션 설정에서 전환하거나 삭제하세요.")
        await postgres.query(
            "DELETE FROM session_participants WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )
        return {"success": True}

    @staticmethod
    async def leave_as_master(postgres: Any, session_id: str, user_id: str) -> dict[str, Any]:
        rows = await postgres.query(
            "SELECT role FROM session_participants WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="세션 참여자가 아닙니다")
        if rows[0]["role"] != "master":
            raise HTTPException(status_code=403, detail="마스터만 이 작업을 수행할 수 있습니다")

        await postgres.query(
            "DELETE FROM session_participants WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )
        next_rows = await postgres.query(
            "SELECT user_id FROM session_participants WHERE session_id = :sid AND user_id != 'bot' ORDER BY joined_at ASC LIMIT 1",
            {"sid": session_id},
        )
        if not next_rows:
            await postgres.update("Session", {"session_id": session_id}, {"is_active": False, "updated_at": datetime.now(tz=timezone.utc)})
            return {"success": True, "deleted": True, "new_master": None}

        new_master_id = next_rows[0]["user_id"]
        await postgres.query(
            "UPDATE session_participants SET role = 'master' WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": new_master_id},
        )
        return {"success": True, "deleted": False, "new_master": new_master_id}

    @staticmethod
    async def get_session_role(postgres: Any, session_id: str, user_id: str) -> Optional[str]:
        rows = await postgres.query(
            "SELECT role FROM session_participants WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )
        return rows[0]["role"] if rows else None

    @staticmethod
    async def get_session_info(postgres: Any, session_id: str) -> dict[str, Any]:
        s_rows = await postgres.query(
            """SELECT s.session_id, s.title, s.topic, s.context_summary,
                      s.is_manual_title, s.created_at, s.trip_id,
                      t.title AS trip_title, t.color AS trip_color, t.is_misc AS trip_is_misc
               FROM sessions s LEFT JOIN trips t ON t.trip_id = s.trip_id
               WHERE s.session_id = :sid""",
            {"sid": session_id},
        )
        session = s_rows[0] if s_rows else {}
        p_rows = await postgres.query(
            """SELECT sp.user_id, sp.role, sp.joined_at, COALESCE(up.nickname, sp.user_id) AS nickname
               FROM session_participants sp LEFT JOIN user_profile up ON up.user_id = sp.user_id
               WHERE sp.session_id = :sid AND sp.user_id != 'bot' ORDER BY sp.joined_at ASC""",
            {"sid": session_id},
        )
        return {
            "session_id": session_id,
            "title": session.get("title", ""),
            "topic": session.get("topic") or "",
            "context_summary": session.get("context_summary") or "",
            "is_manual_title": bool(session.get("is_manual_title", False)),
            "created_at": str(session.get("created_at", "")),
            "trip_id": session.get("trip_id"),
            "trip_title": session.get("trip_title"),
            "trip_color": session.get("trip_color"),
            "trip_is_misc": session.get("trip_is_misc", False),
            "participants": [
                {
                    "user_id": p.get("user_id"),
                    "nickname": p.get("nickname", ""),
                    "role": p.get("role"),
                    "joined_at": str(p.get("joined_at", "")),
                }
                for p in p_rows
            ],
        }

    @staticmethod
    async def get_conversation_history(postgres: Any, session_id: str, limit: int = 40, offset: int = 0) -> list[dict[str, Any]]:
        rows = await postgres.query(
            """SELECT c.sender_id, c.sender_type, c.content, c.created_at,
                      c.message_type, c.message_id,
                      CASE
                        WHEN c.sender_type = 'user'
                          THEN COALESCE(NULLIF(up.nickname, ''), '사용자')
                        ELSE 'AI'
                      END AS sender_name
               FROM conversations c LEFT JOIN user_profile up ON up.user_id = c.sender_id
               WHERE c.session_id = :sid ORDER BY c.created_at DESC LIMIT :lim OFFSET :off""",
            {"sid": session_id, "lim": limit, "off": offset},
        )
        # 파일 메시지가 있으면 session_files에서 safe_name 목록 조회
        msg_ids = [r["message_id"] for r in rows if r.get("message_type") == "file" and r.get("message_id")]
        file_map: dict[str, list[str]] = {}
        if msg_ids:
            placeholders = ", ".join(f":mid{i}" for i in range(len(msg_ids)))
            params = {f"mid{i}": mid for i, mid in enumerate(msg_ids)}
            file_rows = await postgres.query(
                f"SELECT message_id, file_url FROM session_files WHERE message_id IN ({placeholders}) ORDER BY uploaded_at",
                params,
            )
            for fr in file_rows:
                mid = fr["message_id"]
                # file_url에 safe_name만 저장돼 있으므로 그대로 사용
                file_map.setdefault(mid, []).append(fr["file_url"])

        msgs = []
        for row in rows:
            mid = row.get("message_id")
            msgs.append({
                "role": "user" if row.get("sender_type") == "user" else "bot",
                "content": row.get("content", ""),
                "created_at": str(row.get("created_at", "")),
                "sender_id": row.get("sender_id"),
                "sender_name": row.get("sender_name", ""),
                "msg_type": row.get("message_type", "text") or "text",
                "files": file_map.get(mid, []) if mid else [],
            })
        msgs.reverse()
        return msgs

    @staticmethod
    async def save_file_records(postgres: Any, session_id: str, message_id: str, uploader_id: str, safe_names: list, original_names: list) -> None:
        import uuid as _uuid
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        for safe_name, original in zip(safe_names, original_names):
            ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
            file_type = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp") else (f"video/{ext}" if ext in ("mp4", "webm", "ogg", "mov") else "application/octet-stream")
            await postgres.create("SessionFile", {
                "file_id":     "f_" + _uuid.uuid4().hex[:12],
                "session_id":  session_id,
                "message_id":  message_id,
                "uploader_id": uploader_id,
                "file_url":    safe_name,
                "file_name":   original,
                "file_type":   file_type,
                "uploaded_at": now,
            })

    @staticmethod
    async def get_user_teams(postgres: Any, user_id: str) -> list[dict[str, Any]]:
        return await postgres.query(
            "SELECT t.team_id, t.name, t.description, tm.role FROM teams t JOIN team_members tm ON t.team_id = tm.team_id WHERE tm.user_id = :user_id ORDER BY tm.role DESC, t.created_at ASC",
            {"user_id": user_id},
        )

    @staticmethod
    async def create_team(postgres: Any, user_id: str, name: str) -> dict[str, Any]:
        team_id = "team_" + str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc)
        await postgres.create("Team", {"team_id": team_id, "created_by": user_id, "name": name, "created_at": now})
        await postgres.create("TeamMember", {"team_id": team_id, "user_id": user_id, "role": "owner", "joined_at": now})
        return {"team_id": team_id, "name": name, "role": "owner"}

    @staticmethod
    async def get_team_sessions(postgres: Any, team_id: str) -> list[dict[str, Any]]:
        return await postgres.query(
            """SELECT s.session_id, s.title, s.topic, s.created_by,
                      s.trip_id, s.is_manual_title, s.created_at, s.updated_at,
                      tr.color AS trip_color, tr.title AS trip_title
               FROM sessions s
               JOIN trips tr ON s.trip_id = tr.trip_id
               WHERE tr.team_id = :team_id AND s.is_active = true
               ORDER BY s.updated_at DESC""",
            {"team_id": team_id},
        )

    @staticmethod
    async def get_session_participants(postgres: Any, session_id: str) -> list[dict[str, Any]]:
        return await postgres.query(
            """SELECT sp.user_id, sp.role, up.nickname
               FROM session_participants sp
               LEFT JOIN user_profile up ON up.user_id = sp.user_id
               WHERE sp.session_id = :sid AND sp.user_id != 'bot'""",
            {"sid": session_id},
        )

    @staticmethod
    async def remove_non_master_participants(postgres: Any, session_id: str) -> None:
        await postgres.query(
            "DELETE FROM session_participants WHERE session_id = :sid AND role NOT IN ('master', 'bot')",
            {"sid": session_id},
        )

    @staticmethod
    async def get_user_id_by_nickname(postgres: Any, nickname: str) -> Optional[str]:
        rows = await postgres.query(
            "SELECT user_id FROM user_profile WHERE nickname = :nick LIMIT 1",
            {"nick": nickname},
        )
        return rows[0].get("user_id") if rows else None

    @staticmethod
    async def search_users(postgres: Any, q: str, current_user_id: Optional[str] = None) -> dict[str, Any]:
        rows = await postgres.query(
            """SELECT up.user_id, up.nickname, up.email
               FROM user_profile up
               JOIN users u ON up.user_id = u.user_id
               WHERE up.email = :q
                 AND u.status = 'active'
                 AND (:exclude_id IS NULL OR up.user_id != :exclude_id)
               LIMIT 10""",
            {"q": q.strip().lower(), "exclude_id": current_user_id},
        )
        return {"users": rows}

    @staticmethod
    async def invite_to_session(postgres: Any, session_id: str, inviter_id: str, invitee_id: str) -> dict[str, Any]:
        if invitee_id == inviter_id:
            raise HTTPException(status_code=400, detail="자신을 초대할 수 없습니다")
        if await postgres.read("SessionParticipant", {"session_id": session_id, "user_id": invitee_id}):
            raise HTTPException(status_code=409, detail="이미 세션에 참여 중인 사용자입니다")
        nr = await postgres.read("UserProfile", {"user_id": inviter_id})
        inviter_nick = (nr or [{}])[0].get("nickname") or inviter_id
        sr = await postgres.query("SELECT title FROM sessions WHERE session_id = :sid", {"sid": session_id})
        session_title = (sr or [{}])[0].get("title") or "세션"
        notif_id = "notif_" + str(uuid.uuid4())[:12]
        message = f"{inviter_nick}님이 '{session_title}' 세션에 초대했습니다"
        await postgres.create("Notification", {
            "notification_id": notif_id,
            "user_id": invitee_id,
            "type": "session_invite",
            "reference_type": "session",
            "reference_id": session_id,
            "message": message,
            "is_read": False,
            "created_at": datetime.now(tz=timezone.utc),
        })
        return {"notification_id": notif_id, "message": message}

    @staticmethod
    async def save_conversation_message(postgres: Any, msg_data: dict[str, Any]) -> None:
        await postgres.create("Conversation", msg_data)

    @staticmethod
    async def save_notification_record(postgres: Any, notif_data: dict[str, Any]) -> None:
        await postgres.create("Notification", notif_data)

    @staticmethod
    async def get_notifications(postgres: Any, user_id: str) -> list[dict[str, Any]]:
        return await postgres.query(
            """SELECT notification_id, type, reference_type, reference_id,
                      message, is_read, created_at
               FROM notifications
               WHERE user_id = :user_id AND is_read = false
               ORDER BY created_at DESC
               LIMIT 50""",
            {"user_id": user_id},
        )

    @staticmethod
    async def accept_session_invite(postgres: Any, notification_id: str, user_id: str) -> dict[str, Any]:
        rows = await postgres.query(
            "SELECT notification_id, reference_type, reference_id, type FROM notifications WHERE notification_id = :nid AND user_id = :uid",
            {"nid": notification_id, "uid": user_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
        notif = rows[0]
        if notif["type"] != "session_invite" or notif["reference_type"] != "session":
            raise HTTPException(status_code=400, detail="세션 초대 알림이 아닙니다")
        session_id = notif["reference_id"]
        if not await postgres.read("SessionParticipant", {"session_id": session_id, "user_id": user_id}):
            now = datetime.now(tz=timezone.utc)
            await postgres.create("SessionParticipant", {
                "session_id": session_id, "user_id": user_id, "role": "participant", "joined_at": now, "last_read_at": now,
            })
        await postgres.update("Notification", {"notification_id": notification_id}, {"is_read": True})
        return {"success": True, "session_id": session_id}

    @staticmethod
    async def move_session_to_trip(postgres: Any, session_id: str, trip_id: Optional[str], user_id: str) -> dict[str, Any]:
        if trip_id is None:
            trip_id = await Loader.ensure_misc_trip(postgres, user_id)
        await postgres.query(
            """UPDATE sessions SET trip_id = :trip_id, updated_at = :now
               WHERE session_id = :sid
                 AND session_id IN (
                   SELECT session_id FROM session_participants
                   WHERE user_id = :uid AND role = 'master'
                 )""",
            {"trip_id": trip_id, "sid": session_id, "uid": user_id, "now": datetime.now(tz=timezone.utc)},
        )
        return {"success": True}

    @staticmethod
    async def dismiss_notification(postgres: Any, notification_id: str, user_id: str) -> dict[str, Any]:
        await postgres.update("Notification", {"notification_id": notification_id, "user_id": user_id}, {"is_read": True})
        return {"success": True}

    @staticmethod
    async def clear_viewed_notifications(postgres: Any, user_id: str) -> dict[str, Any]:
        await postgres.query(
            "DELETE FROM notifications WHERE user_id = :uid AND is_read = true",
            {"uid": user_id},
        )
        return {"success": True}

    @staticmethod
    async def logout_all_devices(redis: Any, user_id: str) -> None:
        """해당 사용자의 모든 refresh 토큰을 Redis에서 삭제한다."""
        result = await redis.execute({
            "action": "smembers",
            "key": f"user:{user_id}:refresh_jtis",
        })
        jtis = result.get("data", set())
        for jti in jtis:
            await redis.delete(f"auth:refresh:{jti}")
        await redis.delete(f"user:{user_id}:refresh_jtis")

    @staticmethod
    async def mark_session_read(postgres: Any, session_id: str, user_id: str) -> None:
        await postgres.query(
            "UPDATE session_participants SET last_read_at = NOW() WHERE session_id = :sid AND user_id = :uid",
            {"sid": session_id, "uid": user_id},
        )

    @staticmethod
    async def mark_user_deleted(postgres: Any, user_id: str) -> None:
        await postgres.update("User", {"user_id": user_id}, {"status": "deleted"})

    @staticmethod
    async def load_user_to_redis(user_id: str, postgres: Any, redis: Any) -> None:
        from .cacher import Cacher, SESSION_TTL

        result = await Loader.get_settings(postgres, user_id)
        if result.get("profile"):
            await Cacher.save_user_profile(user_id, result["profile"], redis)
        if result.get("style"):
            await Cacher.save_user_style(user_id, result["style"], redis)
        if result.get("travel"):
            await Cacher.save_user_travel(user_id, result["travel"], redis)
        if result.get("data"):
            await Cacher.save_ui_settings(user_id, result["data"], redis)

        # 세션 목록: PG → Redis 권위 로드 (이후 모든 mutation은 Redis-first)
        sessions = await Loader.get_session_list(postgres, user_id, None)
        await redis.set_json(f"user:{user_id}:sessions:all", sessions, SESSION_TTL)

        # 분석 요약 복원: Redis 우선, miss 시 PG analysis 컬럼에서 로드
        analysis = await Cacher.get_user_analysis(user_id, redis)
        if not analysis and result.get("analysis"):
            analysis = result["analysis"]
            await Cacher.save_user_analysis(user_id, analysis, redis)
        elif analysis:
            await redis.execute({
                "action": "hset", "key": f"user:{user_id}:profile",
                "mapping": {"personalized_topics": analysis},
            })

    @staticmethod
    async def flush_user_data(user_id: str, postgres: Any, redis: Any, clear: bool = True) -> None:
        from .cacher import Cacher

        if await Cacher.is_account_deleted(user_id, redis):
            await Loader.mark_user_deleted(postgres, user_id)

        profile = await Cacher.get_user_profile(user_id, redis)
        if profile:
            profile_data = {k: v for k, v in profile.items() if k in ("nickname", "bio", "extra_contacts")}
            if profile_data:
                profile_data["updated_at"] = datetime.now(tz=timezone.utc)
                await postgres.update("UserProfile", {"user_id": user_id}, profile_data)

        for key, column in [("style", "style"), ("travel", "travel"), ("ui", "ui_settings")]:
            value = await getattr(Cacher, f"get_user_{key}" if key != "ui" else "get_ui_settings")(user_id, redis)
            if value:
                await postgres.query(
                    f"""INSERT INTO user_preferences (user_id, {column}, updated_at)
                        VALUES (:uid, CAST(:value AS jsonb), NOW())
                        ON CONFLICT (user_id) DO UPDATE
                        SET {column} = COALESCE(user_preferences.{column}, '{{}}') || CAST(:value AS jsonb),
                            updated_at = NOW()""",
                    {"uid": user_id, "value": json.dumps(value)},
                )

        analysis = await Cacher.get_user_analysis(user_id, redis)
        if analysis:
            await postgres.query(
                """INSERT INTO user_preferences (user_id, analysis, updated_at)
                   VALUES (:uid, :value, NOW())
                   ON CONFLICT (user_id) DO UPDATE
                   SET analysis = :value, updated_at = NOW()""",
                {"uid": user_id, "value": analysis},
            )

        if clear:
            await Cacher.delete_user_data(user_id, redis)
        print(f"[Loader] {user_id} 사용자 데이터 플러시 완료 (clear={clear})")

    @staticmethod
    async def load_session_to_redis(session_id: str, postgres: Any, redis: Any) -> None:
        from .cacher import Cacher
        from .constants import SESSION_TTL

        info = await Loader.get_session_info(postgres, session_id)
        if info:
            await Cacher.cache_session_meta(session_id, {
                "name": info.get("title", ""),
                "topic": info.get("topic", ""),
                "context": info.get("context_summary", ""),
                "is_manual_title": str(info.get("is_manual_title", False)).lower(),
            }, redis)
            trip_id = info.get("trip_id")
            if trip_id:
                await redis.set_str(f"session:{session_id}:trip_id", trip_id, SESSION_TTL)

    @staticmethod
    async def hydrate_messages_to_redis(session_id: str, postgres: Any, redis: Any, limit: int = 40) -> None:
        """Redis `session:{sid}:messages` 가 PG 와 불일치하면 PG 기준으로 풀 hydrate.
        부분 적재 상태에서 새로고침 시 일부 메시지만 노출되는 문제 방지."""
        from .cacher import SESSION_TTL
        key = f"session:{session_id}:messages"
        count_rows = await postgres.query(
            "SELECT COUNT(*)::int AS c FROM conversations WHERE session_id = :sid",
            {"sid": session_id},
        )
        pg_count = (count_rows or [{}])[0].get("c", 0) or 0
        if pg_count == 0:
            return
        cached_len = 0
        if await redis.exists(key):
            cached_len = len(await redis.lrange_json(key, 0, -1))
        if cached_len >= min(pg_count, limit):
            return
        msgs = await Loader.get_conversation_history(postgres, session_id, limit=limit, offset=0)
        await redis.delete(key)
        for m in msgs:
            await redis.rpush_json(key, {
                "message_id":  m.get("message_id", ""),
                "session_id":  session_id,
                "sender_id":   m.get("sender_id") or None,
                "sender_name": m.get("sender_name", ""),
                "sender_type": "user" if m.get("role") == "user" else "ai",
                "message_type": m.get("msg_type") or "text",
                "content":     m.get("content", ""),
                "created_at":  m.get("created_at", ""),
            }, SESSION_TTL)

    @staticmethod
    async def flush_single_session(session_id: str, postgres: Any, redis: Any) -> None:
        """단일 세션의 Redis 메타를 PG로 직접 반영하고 Redis 캐시를 삭제한다."""
        meta_r = await redis.execute({"action": "hgetall", "key": f"session:{session_id}:meta"})
        meta = meta_r.get("data", {})
        if not meta:
            return
        await Loader.update_session_record(postgres, session_id, {
            "title": meta.get("name", "새 세션"),
            "topic": meta.get("topic", ""),
            "context_summary": meta.get("context", ""),
            "is_manual_title": meta.get("is_manual_title", "false") == "true",
        })
        await redis.delete(f"session:{session_id}:meta")

    @staticmethod
    async def flush_user_sessions(user_id: str, postgres: Any, redis: Any) -> None:
        """사용자의 모든 활성 세션을 PG에 직접 플러시하고 Redis 활성 목록을 정리한다."""
        result = await redis.execute({"action": "smembers", "key": f"user:{user_id}:active_sessions"})
        session_ids = set(result.get("data", []))
        for session_id in session_ids:
            try:
                await Loader.flush_single_session(session_id, postgres, redis)
            except Exception as e:
                print(f"[Loader] 세션 {session_id} 플러시 실패: {e}")
            await redis.execute({"action": "srem", "key": f"user:{user_id}:active_sessions", "member": session_id})
        await redis.delete(f"user:{user_id}:current_session")
        print(f"[Loader] {user_id}: {len(session_ids)}개 세션 플러시 완료")

    @staticmethod
    async def flush_dirty_widgets(session_id: str, postgres: Any, redis: Any) -> None:
        result = await redis.execute({"action": "smembers", "key": f"session:{session_id}:dirty_widgets"})
        dirty = set(result.get("data", []))
        if "meta" in dirty:
            meta_r = await redis.execute({"action": "hgetall", "key": f"session:{session_id}:meta"})
            meta = meta_r.get("data", {})
            if meta:
                await Loader.update_session_record(postgres, session_id, {
                    "title": meta.get("name", "새 세션"),
                    "topic": meta.get("topic", ""),
                    "context_summary": meta.get("context", ""),
                    "is_manual_title": meta.get("is_manual_title", "false") == "true",
                })
        if "t_pn" in dirty:
            from .constants import WIDGET_KEY_T_PN
            # trip_id: 전용 캐시 키 → PG 순으로 조회
            trip_id = await redis.get_str(f"session:{session_id}:trip_id")
            if not trip_id:
                rows = await postgres.query(
                    "SELECT trip_id FROM sessions WHERE session_id = :sid",
                    {"sid": session_id},
                )
                trip_id = rows[0].get("trip_id") if rows else None
            scope = f"trip:{trip_id}" if trip_id else f"session:{session_id}"
            t_pn = await redis.get_json(f"{scope}:{WIDGET_KEY_T_PN}") or []
            if t_pn and trip_id:
                await Loader.sync_trip_plan(postgres, trip_id, t_pn)
        if dirty:
            await redis.delete(f"session:{session_id}:dirty_widgets")

    @staticmethod
    async def fetch_user_profile(user_id: str, postgres: Any) -> dict[str, Any]:
        rows = await postgres.read("UserProfile", {"user_id": user_id})
        if not rows:
            return {}
        p = rows[0]
        return {
            "nickname": p.get("nickname", ""),
            "bio": p.get("bio", ""),
            "email1": p.get("email", ""),
            "extra_contacts": p.get("extra_contacts") or [],
        }

    @staticmethod
    async def admin_get_email(postgres: Any, user_id: str) -> str:
        """user_profile.email 조회. 없으면 빈 문자열."""
        rows = await postgres.query("SELECT email FROM user_profile WHERE user_id = :uid", {"uid": user_id})
        return rows[0].get("email", "") if rows else ""

    @staticmethod
    async def get_user_session_topics(postgres: Any, user_id: str, exclude_session_id: str) -> list[str]:
        """사용자의 다른 세션들의 topic을 최신순으로 반환 (UserAnalyze용)."""
        rows = await postgres.query(
            """SELECT s.topic
               FROM sessions s
               JOIN session_participants sp ON sp.session_id = s.session_id
               WHERE sp.user_id = :user_id
                 AND s.session_id != :exclude_id
                 AND s.is_active = true
                 AND s.topic IS NOT NULL AND s.topic != ''
               ORDER BY s.updated_at DESC
               LIMIT 20""",
            {"user_id": user_id, "exclude_id": exclude_session_id},
        )
        return [row["topic"] for row in rows]

    @staticmethod
    async def get_session_participant_count_and_others(
        postgres: Any, session_id: str, exclude_uid: str
    ) -> tuple[int, list[str]]:
        count_rows = await postgres.query(
            "SELECT COUNT(*)::int - 1 AS c FROM session_participants WHERE session_id = :sid",
            {"sid": session_id},
        )
        new_pc = (count_rows or [{}])[0].get("c", 1) or 1
        other_rows = await postgres.query(
            "SELECT user_id FROM session_participants WHERE session_id = :sid AND user_id <> :uid AND user_id <> 'bot'",
            {"sid": session_id, "uid": exclude_uid},
        )
        other_ids = [r.get("user_id") for r in (other_rows or []) if r.get("user_id")]
        return new_pc, other_ids

    @staticmethod
    async def admin_list_users(postgres: Any) -> list[dict]:
        """status != 'deleted' 사용자 목록, user_profile JOIN."""
        return await postgres.query(
            """SELECT u.user_id, u.status, u.created_at, up.nickname, up.email
               FROM users u
               LEFT JOIN user_profile up ON up.user_id = u.user_id
               WHERE u.status != 'deleted'
               ORDER BY u.created_at DESC
               LIMIT 200""",
            {},
        )

    @staticmethod
    async def hydrate_trip_plan_to_redis(session_id: str, postgres: Any, redis: Any) -> None:
        """session_id → trip_id 조회 후 trip 스코프로 t_pn + t_cd hydrate."""
        from .constants import SESSION_TTL
        rows = await postgres.query(
            "SELECT trip_id FROM sessions WHERE session_id = :sid",
            {"sid": session_id},
        )
        trip_id = rows[0].get("trip_id") if rows else None
        if not trip_id:
            return
        await redis.set_str(f"session:{session_id}:trip_id", trip_id, SESSION_TTL)
        await Loader.hydrate_trip_plan_by_trip_id(trip_id, postgres, redis)

    @staticmethod
    async def hydrate_trip_plan_by_trip_id(trip_id: str, postgres: Any, redis: Any) -> None:
        """trip_id로 직접 trip_days + itinerary_items → Redis t_pn + t_cd, kw_bag (이미 캐시됐으면 스킵)."""
        from .constants import DATA_TTL, WIDGET_KEY_T_PN, WIDGET_KEY_T_CD

        scope = f"trip:{trip_id}"
        existing_pn = await redis.get_json(f"{scope}:{WIDGET_KEY_T_PN}") or []
        existing_cd = await redis.get_json(f"{scope}:{WIDGET_KEY_T_CD}") or []
        await Loader.load_trip_kw_bag(trip_id, postgres, redis)
        if existing_pn and existing_cd:
            return

        day_rows = await postgres.query(
            "SELECT day_id, day_number, target_date FROM trip_days WHERE trip_id = :trip_id ORDER BY day_number",
            {"trip_id": trip_id},
        )
        if not day_rows:
            return

        t_pn = []
        t_cd = []
        for day_row in day_rows:
            day_id = day_row["day_id"]
            target_date = day_row.get("target_date")
            if target_date and hasattr(target_date, "year"):
                date_str = f"{target_date.year % 100:02d}{target_date.month:02d}{target_date.day:02d}"
            else:
                date_str = "000000"
            t_cd.append(date_str)

            item_rows = await postgres.query(
                "SELECT visit_order, map_route_data, memo FROM itinerary_items WHERE day_id = :day_id ORDER BY visit_order",
                {"day_id": day_id},
            )
            day_items = [
                {
                    "date":       date_str,
                    "order":      item.get("visit_order", 0),
                    "place":      item.get("memo", ""),
                    "place_info": item.get("map_route_data") or {},
                }
                for item in item_rows
            ]
            t_pn.append(day_items)

        if t_pn and not existing_pn:
            await redis.set_json(f"{scope}:{WIDGET_KEY_T_PN}", t_pn, DATA_TTL)
        if t_cd and not existing_cd:
            await redis.set_json(f"{scope}:{WIDGET_KEY_T_CD}", t_cd, DATA_TTL)

    @staticmethod
    async def sync_trip_plan(postgres: Any, trip_id: str, t_pn: list) -> None:
        """T_PN → trip_days + itinerary_items 전체 교체 동기화.
        기존 trip_days 삭제(CASCADE → itinerary_items 자동 삭제) 후 재삽입.
        """
        if not trip_id or not t_pn:
            return

        # 1) 기존 일정 삭제 (CASCADE로 itinerary_items도 삭제됨)
        await postgres.query(
            "DELETE FROM trip_days WHERE trip_id = :trip_id",
            {"trip_id": trip_id},
        )

        for day_idx, row in enumerate(t_pn):
            if not row:
                continue
            day_number = day_idx + 1

            # 날짜 파싱: YYMMDD → date
            raw_date = (row[0].get("date") or "000000") if isinstance(row[0], dict) else getattr(row[0], "date", "000000")
            try:
                yy, mm, dd = int(raw_date[:2]), int(raw_date[2:4]), int(raw_date[4:6])
                target_date = date(2000 + yy, mm, dd)
            except Exception:
                target_date = date.today()

            day_id = "day_" + str(uuid.uuid4())[:8]
            await postgres.query(
                "INSERT INTO trip_days (day_id, trip_id, day_number, target_date) "
                "VALUES (:day_id, :trip_id, :day_number, :target_date)",
                {"day_id": day_id, "trip_id": trip_id, "day_number": day_number, "target_date": target_date},
            )

            for item in row:
                d = item if isinstance(item, dict) else item.to_dict()
                place_name = d.get("place") or d.get("place_info", {}).get("name", "")
                pi = d.get("place_info") or {}
                route_data = {k: pi.get(k) for k in ("lat", "lng", "address_road", "description", "category") if pi.get(k)}

                item_id = "itm_" + str(uuid.uuid4())[:8]
                route_json = json.dumps(route_data, ensure_ascii=False) if route_data else None
                await postgres.query(
                    "INSERT INTO itinerary_items (item_id, day_id, visit_order, memo, map_route_data, status) "
                    "VALUES (:item_id, :day_id, :visit_order, :memo, CAST(:route AS jsonb), 'proposed')",
                    {
                        "item_id":     item_id,
                        "day_id":      day_id,
                        "visit_order": int(d.get("order", 0)),
                        "memo":        place_name or None,
                        "route":       route_json,
                    },
                )

    @staticmethod
    async def load_trip_kw_bag(trip_id: str, postgres: Any, redis: Any) -> None:
        """trip_keyword_scores → trip:{trip_id}:kw_bag (이미 캐시됐으면 스킵)."""
        from .constants import DATA_TTL
        existing = await redis.get_json(f"trip:{trip_id}:kw_bag")
        if existing is not None:
            return
        rows = await postgres.query(
            "SELECT keyword, score FROM trip_keyword_scores WHERE trip_id = :tid",
            {"tid": trip_id},
        )
        kw_bag = {row["keyword"]: row["score"] for row in rows}
        await redis.set_json(f"trip:{trip_id}:kw_bag", kw_bag, DATA_TTL)

    @staticmethod
    async def save_trip_kw_bag(trip_id: str, kw_bag: dict, postgres: Any) -> None:
        """kw_bag → keyword_encyclopedia + trip_keyword_scores (upsert)."""
        if not kw_bag:
            return
        for keyword, score in kw_bag.items():
            await postgres.query(
                "INSERT INTO keyword_encyclopedia (keyword) VALUES (:kw) ON CONFLICT (keyword) DO NOTHING",
                {"kw": keyword},
            )
            await postgres.query(
                """INSERT INTO trip_keyword_scores (trip_id, keyword, score, updated_at)
                   VALUES (:tid, :kw, :score, NOW())
                   ON CONFLICT (trip_id, keyword)
                   DO UPDATE SET score = :score, updated_at = NOW()""",
                {"tid": trip_id, "kw": keyword, "score": float(score)},
            )

    @staticmethod
    async def reset_trip_plan(trip_id: str, postgres: Any) -> None:
        """trip_days 전체 삭제 (CASCADE → itinerary_items)."""
        await postgres.query(
            "DELETE FROM trip_days WHERE trip_id = :trip_id",
            {"trip_id": trip_id},
        )

    @staticmethod
    async def upsert_trip_day(trip_id: str, day_id: str, day_number: int, target_date: str, postgres: Any) -> None:
        """trip_days row upsert. target_date: YYMMDD."""
        try:
            yy, mm, dd = int(target_date[:2]), int(target_date[2:4]), int(target_date[4:6])
            td = date(2000 + yy, mm, dd)
        except Exception:
            td = date.today()
        await postgres.query(
            """INSERT INTO trip_days (day_id, trip_id, day_number, target_date)
               VALUES (:day_id, :trip_id, :day_number, :target_date)
               ON CONFLICT (day_id) DO UPDATE SET day_number = :day_number, target_date = :target_date""",
            {"day_id": day_id, "trip_id": trip_id, "day_number": day_number, "target_date": td},
        )

    @staticmethod
    async def delete_trip_day(day_id: str, postgres: Any) -> None:
        await postgres.query("DELETE FROM trip_days WHERE day_id = :day_id", {"day_id": day_id})

    @staticmethod
    async def upsert_itinerary_item(day_id: str, item_id: str, visit_order: int, memo: str, map_route_data: dict, postgres: Any) -> None:
        route_json = json.dumps(map_route_data, ensure_ascii=False) if map_route_data else None
        await postgres.query(
            """INSERT INTO itinerary_items (item_id, day_id, visit_order, memo, map_route_data, status)
               VALUES (:item_id, :day_id, :visit_order, :memo, CAST(:route AS jsonb), 'proposed')
               ON CONFLICT (item_id) DO UPDATE SET visit_order = :visit_order, memo = :memo, map_route_data = CAST(:route AS jsonb)""",
            {"item_id": item_id, "day_id": day_id, "visit_order": visit_order, "memo": memo or "", "route": route_json},
        )

    @staticmethod
    async def delete_itinerary_item(item_id: str, postgres: Any) -> None:
        await postgres.query("DELETE FROM itinerary_items WHERE item_id = :item_id", {"item_id": item_id})


# ── 날씨 변화 감지 스케줄러 ──────────────────────────────────────────

def _detect_weather_changes(old_entries: list, new_entries: list) -> list:
    """12시 대표 시간대 기준으로 날씨 변화 감지. 변화 설명 리스트 반환."""
    old_map = {(e["date"], e["time"]): e for e in old_entries}
    changes = []
    for new_e in new_entries:
        if new_e.get("time") != "12":
            continue
        key = (new_e["date"], "12")
        old_e = old_map.get(key)
        if not old_e:
            continue
        mm = new_e["date"][4:6] if len(new_e["date"]) >= 6 else "--"
        dd = new_e["date"][6:8] if len(new_e["date"]) >= 8 else "--"

        if old_e.get("summary") != new_e.get("summary"):
            changes.append(f"{mm}/{dd} {old_e.get('summary','?')} → {new_e.get('summary','?')}")
            continue
        try:
            old_t = float(old_e.get("temperature") or 0)
            new_t = float(new_e.get("temperature") or 0)
            if abs(new_t - old_t) >= 3:
                changes.append(f"{mm}/{dd} 기온 {old_t:.0f}°C→{new_t:.0f}°C")
                continue
        except Exception:
            pass
        try:
            old_r = int(old_e.get("rain_prob") or 0)
            new_r = int(new_e.get("rain_prob") or 0)
            if abs(new_r - old_r) >= 20:
                changes.append(f"{mm}/{dd} 강수확률 {old_r}%→{new_r}%")
        except Exception:
            pass
    return changes


async def _weather_change_loop(pg_adapter: Any, redis_adapter: Any) -> None:
    """24시간마다 날씨 스냅샷을 재조회해 변화 감지 시 알림."""
    from .cacher import Cacher
    from ..execute_unit.system.system_notify import NotifyService

    await asyncio.sleep(3600)  # 앱 시작 1시간 후 첫 실행
    while True:
        try:
            result = await redis_adapter.execute({"action": "smembers", "key": "weather_snapshots:sessions"})
            session_ids = list(result.get("data", set()))

            for session_id in session_ids:
                try:
                    snap = await redis_adapter.get_json(f"session:{session_id}:weather_snapshot")
                    if not snap:
                        await redis_adapter.execute({
                            "action": "srem", "key": "weather_snapshots:sessions", "member": session_id,
                        })
                        continue

                    t_cd       = snap.get("t_cd", [])
                    owner_id   = snap.get("owner_id", "")
                    old_entries = snap.get("entries", [])
                    if not t_cd or not owner_id or not old_entries:
                        continue

                    from ..router.protocol import QUST
                    from ..kernel.ddb import DDB
                    from ..kernel.db_connector import DBConnector

                    qust = QUST(CC="", SSN_TPC=snap.get("ssn_tpc", ""), T_CD=t_cd, T_MK=[], T_PN=[])
                    connector = DBConnector()
                    try:
                        qust = await DDB(connector).run(qust)
                    finally:
                        connector.close()

                    if not qust.dDB:
                        continue

                    new_entries = [
                        {
                            "date":        w.forecast_date,
                            "time":        w.forecast_time,
                            "summary":     w.summary,
                            "rain_prob":   w.rain_prob,
                            "temperature": w.temperature,
                        }
                        for w in qust.dDB
                    ]

                    changes = _detect_weather_changes(old_entries, new_entries)

                    # 스냅샷 항상 최신으로 갱신 (중복 알림 방지)
                    snap["entries"] = new_entries
                    await redis_adapter.set_json(f"session:{session_id}:weather_snapshot", snap, 2592000)

                    if changes:
                        change_text = "; ".join(changes[:3])
                        notif_id   = "notif_" + str(uuid.uuid4())[:12]
                        message    = f"여행 날씨 변경: {change_text}"
                        notif_data = {
                            "notification_id": notif_id,
                            "user_id":         owner_id,
                            "type":            "weather_change",
                            "reference_type":  "session",
                            "reference_id":    session_id,
                            "message":         message,
                            "is_read":         False,
                            "created_at":      datetime.now(tz=timezone.utc).isoformat(),
                        }
                        await Cacher.save_notification(owner_id, notif_data, redis_adapter)
                        NotifyService.push_to_user(owner_id, {
                            "sub_type":  "weather_change",
                            "message":   message,
                            "session_id": session_id,
                        })
                        print(f"[WeatherScheduler] {session_id} 날씨 변화 알림: {change_text}", flush=True)
                except Exception as _e:
                    print(f"[WeatherScheduler] {session_id} 처리 오류: {_e}", flush=True)

        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[WeatherScheduler] 루프 오류: {e}", flush=True)

        await asyncio.sleep(86400)  # 24시간 대기
