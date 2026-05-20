# [역할] 모든 페이지 전환·진입·이탈에 대한 도메인 로직.
#        생명주기 이벤트(open/blur/unload)는 EventHandler로 위임,
#        앱 초기화·설정·UI 상태는 Redis(UserSetting/Cacher)에서 직접 처리.
#
#        호출 방향: SystemUnit → PageService → EventHandler(manager) | UserSetting(Redis)
from datetime import date
from typing import Any, Optional

from ..user.user_setting import UserSetting


class PageService:

    # ── 생명주기 이벤트 ──────────────────────────────────────

    @staticmethod
    async def on_session_open(session_id: str, user_id: str, event_handler: Any) -> None:
        """세션 진입: PG → Redis 로드 보장 (emit_and_wait으로 완료 후 반환)."""
        from ...memory.events import SessionOpenEvent
        await event_handler.emit_and_wait(SessionOpenEvent(session_id=session_id, user_id=user_id))

    @staticmethod
    def on_session_blur(session_id: str, user_id: str, event_handler: Any) -> None:
        """세션 이탈: Redis dirty 위젯 → PG flush (fire-and-forget)."""
        from ...memory.events import SessionBlurEvent
        event_handler.emit(SessionBlurEvent(session_id=session_id, user_id=user_id))

    @staticmethod
    def on_before_unload(user_id: str, event_handler: Any) -> None:
        """창 닫기/새로고침: 전체 플러시 (fire-and-forget)."""
        from ...memory.events import BeforeUnloadEvent
        event_handler.emit(BeforeUnloadEvent(user_id=user_id))

    # ── 앱 초기화 ─────────────────────────────────────────────

    @staticmethod
    async def get_context(user_id: Optional[str], redis: Any) -> dict:
        """
        앱 진입 시 초기 컨텍스트 반환.
        로그인 사용자면 Redis에서 UI 설정 병합, 비로그인은 기본값 반환.
        """
        defaults = {
            "appGlassOpacity":         "20",
            "leftSidebarCustomWidth":   300,
            "rightSidebarCustomWidth":  300,
            "theme":                   "default",
            "appFontKey":              "pretendard",
            "appFontSize":             15,
            "notifications": {
                "response": False,
                "weather":  False,
                "festival": False,
            },
        }
        if user_id:
            saved = await UserSetting.get_ui(user_id, redis)
            for k in ("appGlassOpacity", "leftSidebarCustomWidth", "rightSidebarCustomWidth",
                      "theme", "appFontKey", "appFontSize"):
                if k in saved:
                    defaults[k] = saved[k]
            if isinstance(saved.get("notifications"), dict):
                defaults["notifications"].update(saved["notifications"])
        return {
            "today":    date.today().isoformat(),
            "settings": defaults,
        }

    # ── 설정 페이지 ───────────────────────────────────────────

    @staticmethod
    async def get_settings(user_id: str, redis: Any, manager: Any) -> dict:
        """설정 페이지 진입: 프로필·AI스타일·여행취향·UI 전체 반환."""
        from ...memory.events import CacheMissEvent
        await manager.emit_and_wait(CacheMissEvent(resource="user_profile", user_id=user_id))
        all_settings = await UserSetting.get_all(user_id, redis)
        return {
            "status":   "success",
            "data":     all_settings["ui"],
            "profile":  all_settings["profile"],
            "style":    all_settings["style"],
            "travel":   all_settings["travel"],
            "analysis": all_settings.get("analysis", ""),
        }

    @staticmethod
    async def update_settings(user_id: str, settings: dict, redis: Any) -> dict:
        """UI 설정 부분 업데이트 (테마·투명도·폰트·알림 등)."""
        await UserSetting.save_ui(user_id, settings, redis)
        return {"status": "success"}

    @staticmethod
    async def save_theme(user_id: Optional[str], theme: str, redis: Any) -> dict:
        """테마 즉시 저장. 비로그인은 무시."""
        if user_id:
            await UserSetting.save_ui(user_id, {"theme": theme}, redis)
        return {"status": "success"}

    # ── 기타 페이지 ───────────────────────────────────────────

    @staticmethod
    def get_help() -> dict:
        return {"status": "success", "data": "도움말 가이드라인 페이지입니다."}
