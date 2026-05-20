# [역할] 사용자 설정 도메인.
#        프론트 설정 페이지의 모든 선택지(프로필·AI스타일·여행취향·UI설정)를
#        Redis에 활성 상태로 보유한다. DB 직접 접근 없음.
#        PG 영속화는 logout/beforeunload/idle_sweep 시 Loader.flush_user_data가 처리.
#
#        호출 방향: UserUnit → UserSetting → Cacher(Redis)
from typing import Any

from ...memory.cacher import Cacher


class UserSetting:

    # ── 프로필 (닉네임·소개·이메일·추가 연락수단) ──────────────

    @staticmethod
    async def get_profile(user_id: str, redis: Any) -> dict:
        return await Cacher.get_user_profile(user_id, redis)

    @staticmethod
    async def save_profile(user_id: str, data: dict, redis: Any) -> None:
        await Cacher.save_user_profile(user_id, data, redis)

    # ── AI 스타일·말투 (특성·이모지·헤더·맞춤 지침·추가 정보) ──

    @staticmethod
    async def get_style(user_id: str, redis: Any) -> dict:
        return await Cacher.get_user_style(user_id, redis)

    @staticmethod
    async def save_style(user_id: str, data: dict, redis: Any) -> None:
        await Cacher.save_user_style(user_id, data, redis)

    # ── 여행 취향 (스타일·일정·숙박·음식·알러지·거리·접근성 등) ─

    @staticmethod
    async def get_travel(user_id: str, redis: Any) -> dict:
        return await Cacher.get_user_travel(user_id, redis)

    @staticmethod
    async def save_travel(user_id: str, data: dict, redis: Any) -> None:
        await Cacher.save_user_travel(user_id, data, redis)

    # ── UI 설정 (테마·투명도·폰트·알림 등) ─────────────────────

    @staticmethod
    async def get_ui(user_id: str, redis: Any) -> dict:
        return await Cacher.get_ui_settings(user_id, redis)

    @staticmethod
    async def save_ui(user_id: str, data: dict, redis: Any) -> None:
        await Cacher.save_ui_settings(user_id, data, redis)

    # ── 계정 삭제 마킹 ──────────────────────────────────────────

    @staticmethod
    async def mark_deleted(user_id: str, redis: Any) -> None:
        await Cacher.mark_account_deleted(user_id, redis)

    # ── 계정 정보 ────────────────────────────────────────────────

    @staticmethod
    async def get_account_info(user_id: str, redis: Any) -> dict:
        profile = await Cacher.get_user_profile(user_id, redis)
        return {
            "status":    "success",
            "user_id":   user_id,
            "user_type": user_id.split(":")[0],
            "nickname":  profile.get("nickname", ""),
            "email":     profile.get("email1", profile.get("email", "")),
        }

    # ── 전체 조회 (GET /api/settings 응답용) ────────────────────

    @staticmethod
    async def get_all(user_id: str, redis: Any) -> dict:
        profile  = await Cacher.get_user_profile(user_id, redis)
        style    = await Cacher.get_user_style(user_id, redis)
        travel   = await Cacher.get_user_travel(user_id, redis)
        ui       = await Cacher.get_ui_settings(user_id, redis)
        analysis = await Cacher.get_user_analysis(user_id, redis)
        return {
            "profile": {
                "bio":            profile.get("bio"),
                "nickname":       profile.get("nickname"),
                "email1":         profile.get("email1", profile.get("email")),
                "extra_contacts": profile.get("extra_contacts") or [],
            },
            "style":    style,
            "travel":   travel,
            "ui":       ui,
            "analysis": analysis or "",
        }
