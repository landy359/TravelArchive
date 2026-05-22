# [역할] 팀(Team) CRUD 전담. Cacher만 호출 — Redis 미러링만 본다.
#        모든 PG mutation은 manager(EventHandler)가 위임 처리한다.
#
#        호출 방향: SystemUnit → TeamService → Cacher → (manager) → EventHandler → Loader
from typing import Any

from ...memory.cacher import Cacher


class TeamService:

    @staticmethod
    async def get_team_list(redis: Any, manager: Any, user_id: str) -> list:
        return await Cacher.get_user_teams(user_id, redis, manager)

    @staticmethod
    async def create_team(redis: Any, manager: Any, user_id: str, name: str) -> dict:
        return await Cacher.create_team(user_id, name, redis, manager)

    @staticmethod
    async def get_team_sessions(redis: Any, manager: Any, team_id: str, user_id: str) -> list:
        from fastapi import HTTPException
        teams = await Cacher.get_user_teams(user_id, redis, manager)
        if not any(t.get("team_id") == team_id for t in teams):
            raise HTTPException(status_code=403, detail="팀 멤버만 접근 가능합니다")
        return await Cacher.get_team_sessions(team_id, redis, manager)
