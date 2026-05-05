"""
team_service.py
팀 생성/조회/초대 로직.
회원가입 시 1인 개인 팀 자동 생성, 팀 세션 목록 조회, 세션 초대 처리.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


class TeamService:

    @staticmethod
    async def ensure_personal_team(user_id: str, postgres) -> str:
        """
        사용자의 개인 팀(owner 역할)이 없으면 생성.
        회원가입(MEM/KKO) 직후 호출. 팀 ID 반환.
        """
        result = await postgres.execute({
            "action": "raw_sql",
            "sql": """
                SELECT t.team_id FROM teams t
                JOIN team_members tm ON t.team_id = tm.team_id
                WHERE tm.user_id = :user_id AND tm.role = 'owner'
                LIMIT 1
            """,
            "params": {"user_id": user_id},
        })
        if result.get("status") == "success" and result.get("data"):
            return result["data"][0]["team_id"]

        team_id = "team_" + str(uuid.uuid4())[:8]
        now     = datetime.now(tz=timezone.utc)

        await postgres.execute({
            "action": "create", "model": "Team",
            "data": {
                "team_id":    team_id,
                "created_by": user_id,
                "name":       "내 팀",
                "created_at": now,
            },
        })
        await postgres.execute({
            "action": "create", "model": "TeamMember",
            "data": {
                "team_id":   team_id,
                "user_id":   user_id,
                "role":      "owner",
                "joined_at": now,
            },
        })
        print(f"[TeamService] {user_id}: 개인 팀 생성 → {team_id}")
        return team_id

    @staticmethod
    async def get_user_teams(user_id: str, postgres) -> list:
        """사용자가 속한 모든 팀 목록 반환."""
        result = await postgres.execute({
            "action": "raw_sql",
            "sql": """
                SELECT t.team_id, t.name, t.description, tm.role
                FROM teams t
                JOIN team_members tm ON t.team_id = tm.team_id
                WHERE tm.user_id = :user_id
                ORDER BY tm.role DESC, t.created_at ASC
            """,
            "params": {"user_id": user_id},
        })
        return result.get("data", [])

    @staticmethod
    async def create_team(user_id: str, name: str, postgres) -> dict:
        """새 팀 생성. 생성자는 자동으로 owner."""
        team_id = "team_" + str(uuid.uuid4())[:8]
        now     = datetime.now(tz=timezone.utc)

        await postgres.execute({
            "action": "create", "model": "Team",
            "data": {
                "team_id":    team_id,
                "created_by": user_id,
                "name":       name,
                "created_at": now,
            },
        })
        await postgres.execute({
            "action": "create", "model": "TeamMember",
            "data": {
                "team_id":   team_id,
                "user_id":   user_id,
                "role":      "owner",
                "joined_at": now,
            },
        })
        return {"team_id": team_id, "name": name, "role": "owner"}

    @staticmethod
    async def get_team_sessions(team_id: str, postgres) -> list:
        """팀의 여행에 속한 세션 목록 반환 (trip color 포함)."""
        result = await postgres.execute({
            "action": "raw_sql",
            "sql": """
                SELECT s.session_id, s.title, s.topic, s.created_by,
                       s.trip_id, s."mode", s.is_manual_title,
                       s.created_at, s.updated_at,
                       tr.color AS trip_color, tr.title AS trip_title
                FROM sessions s
                JOIN trips tr ON s.trip_id = tr.trip_id
                WHERE tr.team_id = :team_id AND s.is_active = true
                ORDER BY s.updated_at DESC
            """,
            "params": {"team_id": team_id},
        })
        return result.get("data", [])

    @staticmethod
    async def invite_user_to_session(session_id: str, inviter_id: str,
                                      invitee_id: str, postgres) -> dict:
        """세션 초대 → Notification 생성 (수락 전까지 SessionParticipant 추가 안 함)."""
        if invitee_id == inviter_id:
            raise HTTPException(status_code=400, detail="자신을 초대할 수 없습니다")

        already = await postgres.execute({
            "action":  "read", "model": "SessionParticipant",
            "filters": {"session_id": session_id, "user_id": invitee_id},
        })
        if already.get("status") == "success" and already.get("data"):
            raise HTTPException(status_code=409, detail="이미 세션에 참여 중인 사용자입니다")

        # 중복 초대 방지 — 미읽은 invite 알림이 있으면 재발송 안 함
        pending = await postgres.execute({
            "action": "raw_sql",
            "sql": """
                SELECT notification_id FROM notifications
                WHERE user_id = :uid AND type = 'session_invite'
                  AND reference_type = 'session' AND reference_id = :sid
                  AND is_read = false
                LIMIT 1
            """,
            "params": {"uid": invitee_id, "sid": session_id},
        })
        if pending.get("data"):
            raise HTTPException(status_code=409, detail="이미 초대 알림이 전송되었습니다")

        # 초대자 닉네임 조회
        nr = await postgres.execute({
            "action": "read", "model": "UserProfile",
            "filters": {"user_id": inviter_id},
        })
        inviter_nick = (nr.get("data") or [{}])[0].get("nickname") or inviter_id

        # 세션 제목 조회
        sr = await postgres.execute({
            "action": "raw_sql",
            "sql": "SELECT title FROM sessions WHERE session_id = :sid",
            "params": {"sid": session_id},
        })
        session_title = (sr.get("data") or [{}])[0].get("title") or "세션"

        notif_id = "notif_" + str(uuid.uuid4())[:12]
        now = datetime.now(tz=timezone.utc)
        message = f"{inviter_nick}님이 '{session_title}' 세션에 초대했습니다"
        await postgres.execute({
            "action": "create", "model": "Notification",
            "data": {
                "notification_id": notif_id,
                "user_id":         invitee_id,
                "type":            "session_invite",
                "reference_type":  "session",
                "reference_id":    session_id,
                "message":         message,
                "is_read":         False,
                "created_at":      now,
            },
        })
        # 초대 대상에게 실시간 알림 push
        try:
            from ..router.router import Router
            await Router.push_notification_to_user(invitee_id, {
                "notification_id": notif_id,
                "sub_type":        "session_invite",
                "message":         message,
                "session_id":      session_id,
            })
        except Exception:
            pass

        return {"success": True, "session_id": session_id, "invitee": invitee_id,
                "notification_id": notif_id}
