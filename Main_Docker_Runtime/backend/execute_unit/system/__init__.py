# [역할] 앱 환경·시스템 전반을 처리하는 실행 단위.
#        페이지 이벤트, 세션 CRUD, 여행·팀 관리, 알림, 설정, SSE.
from typing import Any, Optional

from .system_notify import NotifyService
from .system_page import PageService
from .system_team import TeamService
from .system_trip import TripService


class SystemUnit:

    @staticmethod
    async def session_open(session_id: str, user_id: str, manager: Any) -> dict[str, str]:
        await PageService.on_session_open(session_id, user_id, manager)
        return {"status": "ok"}

    @staticmethod
    def session_blur(session_id: str, user_id: str, manager: Any) -> dict[str, str]:
        PageService.on_session_blur(session_id, user_id, manager)
        return {"status": "ok"}

    @staticmethod
    def before_unload(user_id: str, manager: Any) -> dict[str, str]:
        PageService.on_before_unload(user_id, manager)
        return {"status": "ok"}

    @staticmethod
    async def get_context(redis: Any, user_id: Optional[str]) -> dict[str, Any]:
        return await PageService.get_context(user_id, redis)

    @staticmethod
    async def get_settings(redis: Any, user_id: str, manager: Any) -> dict[str, Any]:
        return await PageService.get_settings(user_id, redis, manager)

    @staticmethod
    async def update_settings(user_id: str, settings: dict[str, Any], redis: Any) -> dict[str, str]:
        return await PageService.update_settings(user_id, settings, redis)

    @staticmethod
    async def save_theme(user_id: Optional[str], theme: str, redis: Any) -> dict[str, str]:
        return await PageService.save_theme(user_id, theme, redis)

    @staticmethod
    def get_help() -> dict[str, str]:
        return PageService.get_help()

    @staticmethod
    async def get_session_list(trip_id: Optional[str], user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.get_session_list(trip_id, user_id, redis, manager)

    @staticmethod
    async def create_session(user_id: str, trip_id: Optional[str], redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.create_session(user_id, trip_id, redis, manager)

    @staticmethod
    async def delete_session(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.delete_session(session_id, user_id, redis, manager)

    @staticmethod
    async def leave_session(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, bool]:
        from ..chat.chat_service import ChatService
        return await ChatService.leave_session(session_id, user_id, redis, manager)

    @staticmethod
    async def convert_to_personal(session_id: str, user_id: str, redis: Any, manager: Any) -> dict[str, bool]:
        from ..chat.chat_service import ChatService
        return await ChatService.convert_to_personal(session_id, user_id, redis, manager)

    @staticmethod
    async def update_session_title(session_id: str, title: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.update_session_title(session_id, title, user_id, redis, manager)

    @staticmethod
    async def update_session_color(session_id: str, color: str, user_id: str, redis: Any, manager: Any) -> dict[str, str]:
        from ..chat.chat_service import ChatService
        return await ChatService.update_session_color(session_id, color, user_id, redis, manager)

    @staticmethod
    async def get_session_info(redis: Any, manager: Any, session_id: str) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.get_session_info(redis, manager, session_id)

    @staticmethod
    async def move_session_to_trip(redis: Any, manager: Any, session_id: str, trip_id: Optional[str], user_id: str) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.move_session_to_trip(redis, manager, session_id, trip_id, user_id)

    @staticmethod
    async def mark_session_read(redis: Any, manager: Any, session_id: str, user_id: str) -> dict[str, bool]:
        from ..chat.chat_service import ChatService
        await ChatService.mark_session_read(redis, manager, session_id, user_id)
        return {"success": True}

    @staticmethod
    async def invite_user(session_id: str, invitee: str, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.invite_user(session_id, invitee, user_id, redis, manager)

    @staticmethod
    async def share_chat(session_id: str, user_id: str, redis: Any) -> dict[str, str | bool]:
        from ..chat.chat_service import ChatService
        return await ChatService.share_chat(session_id, user_id, redis)

    @staticmethod
    async def search_users(redis: Any, manager: Any, q: str, user_id: str) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.search_users(redis, manager, q, user_id)

    @staticmethod
    async def download_chat(session_id: str, redis: Any, manager: Any) -> Any:
        from ..chat.chat_service import ChatService
        return await ChatService.download_chat(session_id, redis, manager)

    @staticmethod
    async def upload_files(session_id: str, files: Any, user_id: str, redis: Any, manager: Any) -> dict[str, Any]:
        from ..chat.chat_service import ChatService
        return await ChatService.upload_files(session_id, files, user_id, redis, manager)

    @staticmethod
    async def subscribe_session_events(session_id: str, user_id: str) -> Any:
        return await NotifyService.subscribe_session_events(session_id, user_id)

    @staticmethod
    async def subscribe_user_notifications(user_id: str) -> Any:
        return await NotifyService.subscribe_user_notifications(user_id)

    @staticmethod
    def get_active_session_info() -> list:
        return NotifyService.get_active_session_info()

    @staticmethod
    async def get_trip_list(redis: Any, manager: Any, user_id: str) -> dict[str, Any]:
        trips = await TripService.get_trip_list(redis, manager, user_id)
        return {"trips": trips}

    @staticmethod
    async def create_trip(redis: Any, manager: Any, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await TripService.create_trip(redis, manager, user_id, data)

    @staticmethod
    async def update_trip(redis: Any, manager: Any, trip_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await TripService.update_trip(redis, manager, trip_id, user_id, data)

    @staticmethod
    async def delete_trip(redis: Any, manager: Any, trip_id: str, user_id: str) -> dict[str, Any]:
        return await TripService.delete_trip(redis, manager, trip_id, user_id)

    @staticmethod
    async def get_team_list(redis: Any, manager: Any, user_id: str) -> dict[str, Any]:
        teams = await TeamService.get_team_list(redis, manager, user_id)
        return {"teams": teams}

    @staticmethod
    async def create_team(redis: Any, manager: Any, user_id: str, name: str) -> dict[str, Any]:
        return await TeamService.create_team(redis, manager, user_id, name)

    @staticmethod
    async def get_team_sessions(redis: Any, manager: Any, team_id: str, user_id: str) -> dict[str, Any]:
        sessions = await TeamService.get_team_sessions(redis, manager, team_id, user_id)
        return {"sessions": sessions}

    @staticmethod
    async def get_notifications(user_id: str, redis: Any, manager: Any) -> list[dict[str, Any]]:
        return await NotifyService.get_user_notifications(user_id, redis, manager)

    @staticmethod
    async def accept_session_invite(redis: Any, manager: Any, notification_id: str, user_id: str) -> dict[str, Any]:
        return await NotifyService.accept_session_invite(redis, manager, notification_id, user_id)

    @staticmethod
    async def dismiss_notification(redis: Any, manager: Any, notification_id: str, user_id: str) -> dict[str, bool]:
        await NotifyService.dismiss_notification(redis, manager, notification_id, user_id)
        return {"success": True}

    @staticmethod
    async def clear_viewed_notifications(redis: Any, manager: Any, user_id: str) -> dict[str, bool]:
        await NotifyService.clear_viewed_notifications(redis, manager, user_id)
        return {"success": True}
