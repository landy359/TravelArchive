# [역할] 사용자 데이터(프로필·AI스타일·여행취향·UI설정·계정 삭제)를 처리하는 실행 단위.
#        DB를 전혀 모른다. UserSetting 도메인을 통해 Redis에만 쓴다.
#        save_* 호출 시 SaveSettingsEvent를 emit → EventHandler가 PG flush.
#
#        호출 방향: Facade → UserUnit → UserSetting → Cacher(Redis)
#                                     → EventHandler(SaveSettingsEvent) → Loader → PG
import asyncio
from typing import Any, Optional

from .user_setting import UserSetting
from ...memory.events import AccountDeleteEvent, SaveSettingsEvent

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


class UserUnit:

    @staticmethod
    async def get_account_info(redis: Any, user_id: Optional[str]) -> dict:
        if not user_id:
            return {"status": "unauthenticated", "user_id": None}
        return await UserSetting.get_account_info(user_id, redis)

    @staticmethod
    async def save_profile(user_id: str, data: dict, redis: Any, manager: Any = None) -> dict:
        await UserSetting.save_profile(user_id, data, redis)
        if manager:
            manager.emit(SaveSettingsEvent(user_id=user_id))
        return {"status": "success"}

    @staticmethod
    async def save_style(user_id: str, data: dict, redis: Any, manager: Any = None) -> dict:
        await UserSetting.save_style(user_id, data, redis)
        if manager:
            manager.emit(SaveSettingsEvent(user_id=user_id))
            from .user_analyze import UserAnalyze
            _spawn(UserAnalyze.run_on_settings_change(user_id, data, {}, redis, manager))
        return {"status": "success"}

    @staticmethod
    async def save_travel(user_id: str, data: dict, redis: Any, manager: Any = None) -> dict:
        await UserSetting.save_travel(user_id, data, redis)
        if manager:
            manager.emit(SaveSettingsEvent(user_id=user_id))
            from .user_analyze import UserAnalyze
            _spawn(UserAnalyze.run_on_settings_change(user_id, {}, data, redis, manager))
        return {"status": "success"}

    @staticmethod
    async def delete_account(user_id: str, redis: Any, manager: Any) -> dict:
        await UserSetting.mark_deleted(user_id, redis)
        manager.emit(AccountDeleteEvent(user_id=user_id))
        return {"status": "success", "message": "계정이 삭제되었습니다"}
