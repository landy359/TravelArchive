# [역할] MemoryManager와 Execute Unit 사이의 이벤트 타입 정의 모음.
#        실행 단위가 manager.emit(XxxEvent(...))으로 생명주기 신호를 보낼 때 사용하는 데이터 구조.
#        로직 없음. 순수 데이터 컨테이너만 정의한다.
#
#        흐름: Execute Unit → manager.emit(Event) → MemoryManager._dispatch → 핸들러
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LoginEvent:
    user_id: str

@dataclass
class LogoutEvent:
    user_id: str

@dataclass
class SignupEvent:
    user_id: str

@dataclass
class BeforeUnloadEvent:
    user_id: str

@dataclass
class SessionOpenEvent:
    session_id: str
    user_id: str

@dataclass
class SessionBlurEvent:
    session_id: str
    user_id: str

@dataclass
class WidgetChangeEvent:
    session_id: str
    widget_type: str   # "markers" | "routes" | "ranges"

@dataclass
class CacheMissEvent:
    resource: str      # "user_profile" | "session_meta" | "ui_settings"
    user_id: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class AccountDeleteEvent:
    user_id: str


# ── Auth 요청 이벤트 (Future 기반, priority queue 전용) ──────────

@dataclass
class LoginRequestEvent:
    email:    str
    password: str
    future:   asyncio.Future

@dataclass
class LogoutRequestEvent:
    """flush + token revoke를 한 번에 처리. LogoutEvent(background)와 별개."""
    refresh_token: str
    user_id:       Optional[str]
    future:        asyncio.Future

@dataclass
class SignupRequestEvent:
    data:   dict
    future: asyncio.Future

@dataclass
class RefreshRequestEvent:
    refresh_token: str
    future:        asyncio.Future

@dataclass
class GetMyInfoRequestEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class SaveSettingsEvent:
    """사용자 설정 저장 버튼 클릭 → Redis → PG 즉시 flush."""
    user_id: str

@dataclass
class KakaoAuthRequestEvent:
    """카카오 OAuth 콜백 처리 — 사용자 조회/생성 및 JWT 발급."""
    provider_uid:    str
    nickname:        str
    email:           Optional[str]
    profile_img_url: str
    redis:           Any
    state:           Optional[str]
    future:          asyncio.Future


# ── 캐시 미스 복구 이벤트 (Future 기반) ─────────────────────────
# execute_unit이 Cacher(Redis)에서 빈 결과를 받으면 이 이벤트로
# EventHandler → Loader → Redis 워밍 → Future 해소.

@dataclass
class LoadUserProfileEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class LoadSessionListEvent:
    user_id:  str
    trip_id:  Optional[str]
    future:   asyncio.Future

@dataclass
class LoadTripListEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class LoadTeamListEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class LoadTeamSessionsEvent:
    team_id: str
    future:  asyncio.Future

@dataclass
class LoadNotificationsEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class LoadMessagesEvent:
    session_id: str
    limit:      int
    offset:     int
    future:     asyncio.Future

@dataclass
class LoadSessionParticipantsEvent:
    session_id: str
    future:     asyncio.Future

@dataclass
class GetSessionInfoEvent:
    session_id: str
    future:     asyncio.Future

@dataclass
class SearchUsersEvent:
    q:       str
    user_id: str
    future:  asyncio.Future

@dataclass
class GetMiscTripEvent:
    """기타 여행 ID 조회/생성."""
    user_id: str
    future:  asyncio.Future

@dataclass
class GetSessionRoleEvent:
    session_id: str
    user_id:    str
    future:     asyncio.Future

@dataclass
class GetUserByNicknameEvent:
    nickname: str
    future:   asyncio.Future


# ── DB 쓰기 이벤트 ───────────────────────────────────────────────
# execute_unit이 Redis에 저장 후 PG 영속화가 필요할 때 emit.
# 응답이 필요한 경우 future 포함, fire-and-forget은 future 없음.

@dataclass
class SaveMessageEvent:
    """메시지를 PG에 영속화 (fire-and-forget)."""
    session_id: str
    msg_data:   dict

@dataclass
class SaveNotificationEvent:
    """알림을 PG에 영속화 (fire-and-forget)."""
    user_id:    str
    notif_data: dict

@dataclass
class CreateSessionEvent:
    session_id: str
    user_id:    str
    data:       dict
    future:     asyncio.Future

@dataclass
class LeaveSessionEvent:
    """세션 탈퇴 — PG 업데이트 (fire-and-forget)."""
    session_id: str
    user_id:    str

@dataclass
class LeaveAsMasterEvent:
    session_id: str
    user_id:    str
    future:     asyncio.Future

@dataclass
class UpdateSessionRecordEvent:
    """세션 메타 PG 업데이트 (fire-and-forget)."""
    session_id: str
    data:       dict

@dataclass
class RemoveNonMasterEvent:
    """팀 세션 개인 전환 — 비마스터 참여자 제거 (fire-and-forget)."""
    session_id: str

@dataclass
class InviteUserEvent:
    session_id: str
    inviter_id: str
    invitee:    str
    future:     asyncio.Future

@dataclass
class MoveSessionTripEvent:
    session_id: str
    trip_id:    Optional[str]
    user_id:    str
    future:     asyncio.Future

@dataclass
class MarkReadEvent:
    """읽음 처리 PG 업데이트 (fire-and-forget)."""
    session_id: str
    user_id:    str

@dataclass
class CreateTripEvent:
    user_id: str
    data:    dict
    future:  asyncio.Future

@dataclass
class UpdateTripEvent:
    trip_id: str
    user_id: str
    data:    dict
    future:  asyncio.Future

@dataclass
class DeleteTripEvent:
    trip_id: str
    user_id: str
    future:  asyncio.Future

@dataclass
class CreateTeamEvent:
    user_id: str
    name:    str
    future:  asyncio.Future

@dataclass
class AcceptInviteEvent:
    notification_id: str
    user_id:         str
    future:          asyncio.Future

@dataclass
class DismissNotifEvent:
    """알림 무시 (fire-and-forget)."""
    notification_id: str
    user_id:         str

@dataclass
class ClearNotifsEvent:
    """읽은 알림 전체 삭제 (fire-and-forget)."""
    user_id: str

@dataclass
class LogoutAllDevicesEvent:
    """모든 기기 로그아웃 — Redis의 auth:refresh:{jti} 키를 pattern 스캔 후 전부 삭제."""
    user_id: str
    future:  asyncio.Future

@dataclass
class AdminCheckEmailEvent:
    user_id: str
    future:  asyncio.Future

@dataclass
class AdminListUsersEvent:
    future:  asyncio.Future


# ── 사용자 분석 이벤트 ──────────────────────────────────────────────

@dataclass
class LoadUserSessionTopicsEvent:
    """UserAnalyze가 PG에서 사용자의 다른 세션 주제 목록을 가져올 때."""
    user_id:            str
    exclude_session_id: str
    future:             asyncio.Future
