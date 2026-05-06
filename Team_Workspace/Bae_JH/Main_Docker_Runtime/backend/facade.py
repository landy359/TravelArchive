"""
facade.py
TravelArchive 백엔드 진입점 — 프론트엔드와의 연결만 담당.

인증 구조:
  - 로그인(MEM/KKO): 모든 기능 해금
  - 비로그인: /api/temp/{id}/message 임시 챗봇만 사용 가능
  - 게스트(GST) 개념 없음

@app 라우트를 모두 정의하되 함수 본문은 두 클래스에 위임합니다.
  Loader  (backend/loader/)  — DB 접근이 필요한 모든 작업
  Router  (backend/router/)  — 세션·채팅·지도·메모·플래너 작업
"""

import os
import sys
import random
from typing import Dict, List, Optional
from datetime import date
from dotenv import load_dotenv

# ── 경로 설정 ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, "setting", ".env"))

# ── FastAPI / Pydantic ───────────────────────────────────────
from fastapi import FastAPI, Request, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 내부 모듈 ────────────────────────────────────────────────
from .loader.loader import Loader
from .router.router import Router
from .auth.dependencies import get_current_user, get_optional_user


# ============================================================
# FastAPI 앱
# ============================================================

app = FastAPI(title="TravelArchive API", lifespan=Loader.lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Pydantic 요청 모델
# ============================================================

class SignUpRequest(BaseModel):
    email: str
    password: str
    nickname: str = ""

class LoginRequest(BaseModel):
    id: str
    pw: str

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class TempMessageRequest(BaseModel):
    message: str

class SessionCreateRequest(BaseModel):
    first_message: str
    trip_id: Optional[str] = None
    plan_id: Optional[str] = None  # 하위 호환 (trip_id 별칭)

class SessionColorUpdateRequest(BaseModel):
    color: str

class InviteRequest(BaseModel):
    user: str

class TitleUpdateRequest(BaseModel):
    title: str

class SessionTripUpdateRequest(BaseModel):
    trip_id: Optional[str] = None  # None = 기타로 이동

class MessageRequest(BaseModel):
    message: str

class ThemeRequest(BaseModel):
    theme: str

class MapMarkersRequest(BaseModel):
    markers: List[Dict]

class MapMarkerAddRequest(BaseModel):
    marker_id: str
    lat: float
    lng: float
    title: Optional[str] = None

class MapRoutesRequest(BaseModel):
    marker_ids: List[str]

class MemoRequest(BaseModel):
    memo: str

class PlanRequest(BaseModel):
    plan: List[Dict]

class TripRangeRequest(BaseModel):
    ranges: List[Dict]

class TripCreateRequest(BaseModel):
    title: str
    color: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class TripUpdateRequest(BaseModel):
    title: Optional[str] = None
    color: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None

class TeamCreateRequest(BaseModel):
    name: str

class UserProfileRequest(BaseModel):
    nickname: Optional[str] = None
    bio: Optional[str] = None
    email1: Optional[str] = None
    extra_contacts: Optional[List[str]] = None

class UserStyleRequest(BaseModel):
    characteristics: Optional[List[str]] = None
    emoji_usage: Optional[str] = None
    header_usage: Optional[str] = None
    custom_instructions: Optional[str] = None
    additional_info: Optional[str] = None

class UserTravelRequest(BaseModel):
    styles: Optional[List[str]] = None
    pace: Optional[str] = None
    accommodations: Optional[List[str]] = None
    food_prefs: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    max_distance: Optional[int] = None
    distance_unit: Optional[str] = None
    weather_crowd: Optional[bool] = None
    pet_friendly: Optional[bool] = None
    disabilities: Optional[List[str]] = None
    disability_other: Optional[str] = None


# ============================================================
# 비로그인 임시 챗봇 API  (인증 불필요)
# ============================================================

@app.post("/api/temp/{temp_session_id}/message")
async def send_temp_message(temp_session_id: str, req: TempMessageRequest):
    """
    비로그인 또는 로그인 후 임시채팅.
    - 인증 없이 사용 가능
    - DB/Redis 저장 없음 — 새로고침 시 사라짐
    """
    return await Router.send_temp_message(temp_session_id, req.message)


# ============================================================
# 인증 API  →  Loader
# ============================================================

@app.post("/api/auth/signup")
async def signup(req: SignUpRequest, request: Request):
    return await Loader.signup(request.app.state.postgres,
                               {"email": req.email, "password": req.password, "nickname": req.nickname})

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    return await Loader.login(request.app.state.postgres, request.app.state.redis, req.id, req.pw)

@app.post("/api/auth/refresh")
async def refresh(req: RefreshRequest, request: Request):
    return await Loader.refresh_token(request.app.state.redis, req.refresh_token)

@app.post("/api/auth/logout")
async def logout(req: LogoutRequest, request: Request,
                 user_id: Optional[str] = Depends(get_optional_user)):
    """로그아웃: 세션 플러시 후 Refresh Token 폐기."""
    await Loader.logout(request.app.state.postgres, request.app.state.redis,
                        req.refresh_token, user_id)
    return {"status": "success", "message": "로그아웃 되었습니다"}

@app.post("/api/auth/logout/all")
async def logout_all_devices(req: LogoutRequest, request: Request,
                              user_id: str = Depends(get_current_user)):
    await Loader.logout(request.app.state.postgres, request.app.state.redis,
                        req.refresh_token, user_id)
    return {"status": "success", "message": "모든 기기에서 로그아웃되었습니다"}

# ── 카카오 OAuth ─────────────────────────────────────────────

@app.get("/api/auth/kakao")
async def kakao_login_redirect():
    from .auth.oauth_service import get_kakao_auth_url
    return RedirectResponse(get_kakao_auth_url())

@app.get("/api/auth/kakao/callback")
async def kakao_callback(code: str, request: Request, state: Optional[str] = None):
    from .auth.oauth_service import kakao_callback as _kakao_callback
    result = await _kakao_callback(code, request.app.state.postgres, request.app.state.redis, state)

    # 계정 연동 처리 결과
    if result.get("linked"):
        return RedirectResponse("/?kakao_linked=1")

    # 카카오 첫 로그인 시 개인 팀 보장
    try:
        from .system.team_service import TeamService
        await TeamService.ensure_personal_team(result["user_id"], request.app.state.postgres)
    except Exception:
        pass
    from urllib.parse import quote
    redirect_url = (
        f"/?access_token={result['access_token']}"
        f"&refresh_token={result['refresh_token']}"
        f"&user_id={quote(result.get('user_id', ''))}"
        f"&user_type={result['type']}"
        f"&nickname={quote(result.get('nickname', ''))}"
        f"&email={quote(result.get('email', '') or '')}"
    )
    return RedirectResponse(redirect_url)

@app.get("/api/auth/kakao/link")
async def kakao_link_redirect(request: Request, user_id: str = Depends(get_current_user)):
    """로그인된 사용자의 카카오 계정 연동 시작 — state에 link 토큰 포함."""
    from .auth.oauth_service import initiate_kakao_link
    url = await initiate_kakao_link(user_id, request.app.state.redis)
    return RedirectResponse(url)

@app.post("/api/auth/social/link/kakao")
async def link_kakao_account(request: Request, user_id: str = Depends(get_current_user)):
    """연동 시작 URL을 JSON으로 반환 (프론트에서 window.location 이동 전용)."""
    from .auth.oauth_service import initiate_kakao_link
    url = await initiate_kakao_link(user_id, request.app.state.redis)
    return {"status": "ok", "redirect_url": url}

@app.post("/api/auth/find")
async def find_account():
    return {"status": "not_implemented"}

@app.get("/api/auth/me")
async def get_my_info(request: Request, user_id: str = Depends(get_current_user)):
    return await Loader.get_my_info(request.app.state.postgres, user_id)


# ============================================================
# 세션 플러시 API  (창 닫기 / beforeunload 전용)
# ============================================================

@app.post("/api/sessions/flush")
async def flush_sessions(request: Request, user_id: str = Depends(get_current_user)):
    """beforeunload 또는 명시적 플러시 요청 시 Redis → Postgres 저장."""
    from .system.flush_service import FlushService
    await FlushService.flush_user_sessions(
        user_id, request.app.state.postgres, request.app.state.redis)
    return {"status": "success"}


# ============================================================
# 계정 / 설정 / 컨텍스트 / 날씨 / 도움말  →  Loader
# ============================================================

@app.get("/api/account")
async def get_account_info(request: Request, user_id: str = Depends(get_optional_user)):
    return await Loader.get_account_info(request.app.state.postgres, user_id)

@app.put("/api/user/profile")
async def save_user_profile(req: UserProfileRequest, request: Request,
                             user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if data:
        await request.app.state.postgres.execute({
            "action": "update", "model": "UserProfile",
            "filters": {"user_id": user_id},
            "data": {k: v for k, v in {
                "nickname": data.get("nickname"),
            }.items() if v is not None},
        })
    return {"status": "success"}

@app.put("/api/user/style")
async def save_user_style(req: UserStyleRequest, request: Request,
                           user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if data:
        await request.app.state.postgres.execute({
            "action": "update", "model": "UserPreferences",
            "filters": {"user_id": user_id},
            "data": {"ui_settings": data},
        })
    return {"status": "success"}

@app.put("/api/user/travel")
async def save_travel_preferences(req: UserTravelRequest, request: Request,
                                   user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if data:
        update = {}
        if "styles" in data:     update["travel_style"]     = ",".join(data["styles"])
        if "food_prefs" in data: update["preferred_food"]   = data["food_prefs"]
        if "pace" in data:       update["schedule_density"] = data["pace"]
        if data:
            update["personalized_topics"] = data
        await request.app.state.postgres.execute({
            "action": "update", "model": "UserPreferences",
            "filters": {"user_id": user_id},
            "data": update,
        })
    return {"status": "success"}

@app.delete("/api/user/account")
async def delete_account(request: Request, user_id: str = Depends(get_current_user)):
    await request.app.state.postgres.execute({
        "action": "update", "model": "User",
        "filters": {"user_id": user_id},
        "data": {"status": "deleted"},
    })
    return {"status": "success", "message": "계정이 삭제되었습니다"}

@app.get("/api/context")
async def get_app_context():
    return {
        "today": date.today().isoformat(),
        "settings": {
            "appGlassOpacity":        "20",
            "leftSidebarCustomWidth":  300,
            "rightSidebarCustomWidth": 300,
            "theme":                  "default",
        },
    }

@app.get("/api/settings")
async def get_settings(request: Request, user_id: str = Depends(get_current_user)):
    return await Loader.get_settings(user_id)

@app.post("/api/settings/update")
async def update_settings(settings: Dict[str, str], request: Request,
                           user_id: str = Depends(get_current_user)):
    return await Loader.update_settings(user_id, settings)

@app.get("/api/help")
async def get_help_data():
    return {"status": "success", "data": "도움말 가이드라인 페이지입니다."}

@app.post("/api/theme")
async def save_theme_preference(req: ThemeRequest, user_id: str = Depends(get_optional_user)):
    return {"status": "success"}

@app.get("/api/weather")
async def get_weather():
    selected = random.choice(["clear", "cloudy", "rain", "night"])
    return {
        "type": selected,
        "params": {
            "intensity":     round(random.uniform(0.2, 1.5), 2),
            "windDirection": round(random.uniform(-1.0, 1.0), 2),
            "cloudDensity":  random.randint(3, 10),
            "starDensity":   random.randint(100, 300),
        },
    }


# ============================================================
# 여행(Trip) API  →  Loader  (로그인 필수)
# ============================================================

@app.get("/api/trips")
async def get_trip_list(request: Request, user_id: str = Depends(get_current_user)):
    trips = await Loader.get_trip_list(request.app.state.postgres, user_id)
    return {"trips": trips}

@app.post("/api/trips")
async def create_trip(req: TripCreateRequest, request: Request,
                       user_id: str = Depends(get_current_user)):
    return await Loader.create_trip(request.app.state.postgres, user_id, req.model_dump(exclude_none=True))

@app.put("/api/trips/{trip_id}")
async def update_trip(trip_id: str, req: TripUpdateRequest, request: Request,
                       user_id: str = Depends(get_current_user)):
    return await Loader.update_trip(request.app.state.postgres, trip_id, user_id,
                                     req.model_dump(exclude_none=True))

@app.delete("/api/trips/{trip_id}")
async def delete_trip(trip_id: str, request: Request,
                       user_id: str = Depends(get_current_user)):
    return await Loader.delete_trip(request.app.state.postgres, trip_id, user_id)

# 하위 호환: /api/plans → /api/trips 리다이렉트 대신 동일 응답
@app.get("/api/plans")
async def get_plan_list(request: Request, user_id: str = Depends(get_current_user)):
    trips = await Loader.get_trip_list(request.app.state.postgres, user_id)
    return {"trips": trips, "plans": trips}  # 하위 호환


# ============================================================
# 팀(Team) API  →  Loader  (로그인 필수)
# ============================================================

@app.get("/api/teams")
async def get_team_list(request: Request, user_id: str = Depends(get_current_user)):
    teams = await Loader.get_team_list(request.app.state.postgres, user_id)
    return {"teams": teams}

@app.post("/api/teams")
async def create_team(req: TeamCreateRequest, request: Request,
                       user_id: str = Depends(get_current_user)):
    return await Loader.create_team(request.app.state.postgres, user_id, req.name)

@app.get("/api/teams/{team_id}/sessions")
async def get_team_sessions(team_id: str, request: Request,
                             user_id: str = Depends(get_current_user)):
    sessions = await Loader.get_team_sessions(request.app.state.postgres, team_id)
    return {"sessions": sessions}


# ============================================================
# 세션 관리 API  →  Router  (로그인 필수)
# ============================================================

@app.get("/api/sessions")
async def get_session_list(request: Request,
                            trip_id: Optional[str] = None,
                            plan_id: Optional[str] = None,  # 하위 호환
                            user_id: str = Depends(get_current_user)):
    effective_trip = trip_id or plan_id
    return await Router.get_session_list(effective_trip, user_id, request.app.state.postgres)

@app.post("/api/sessions")
async def create_session(req: SessionCreateRequest, request: Request,
                          user_id: str = Depends(get_current_user)):
    effective_trip = req.trip_id or req.plan_id
    return await Router.create_session(
        req.first_message, None, user_id, effective_trip,
        request.app.state.postgres, request.app.state.redis)

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request,
                          user_id: str = Depends(get_current_user)):
    """마스터 전용: 세션 삭제 (팀원 전원 kicked 후 비활성화)."""
    return await Router.delete_session(session_id, user_id,
                                        request.app.state.postgres, request.app.state.redis)

@app.post("/api/sessions/{session_id}/leave")
async def leave_session(session_id: str, request: Request,
                         user_id: str = Depends(get_current_user)):
    """팀원 전용: 본인 탈퇴."""
    return await Router.leave_session(session_id, user_id,
                                       request.app.state.postgres, request.app.state.redis)

@app.post("/api/sessions/{session_id}/convert-personal")
async def convert_to_personal(session_id: str, request: Request,
                               user_id: str = Depends(get_current_user)):
    """마스터 전용: 팀원 전원 퇴장 후 개인 세션으로 전환."""
    return await Router.convert_to_personal(session_id, user_id,
                                             request.app.state.postgres,
                                             request.app.state.redis)

@app.get("/api/users/search")
async def search_users(q: str, request: Request, user_id: str = Depends(get_current_user)):
    """닉네임으로 사용자 검색 (자신 제외)."""
    return await Loader.search_users(request.app.state.postgres, q, user_id)

@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request,
                          user_id: str = Depends(get_current_user)):
    """팀 채팅 실시간 이벤트 스트림 (SSE)."""
    return await Router.subscribe_session_events(session_id, user_id)

@app.post("/api/sessions/{session_id}/invite")
async def invite_user(session_id: str, req: InviteRequest, request: Request,
                      user_id: str = Depends(get_current_user)):
    return await Router.invite_user(session_id, req.user, user_id,
                                     request.app.state.postgres)

@app.post("/api/sessions/{session_id}/share")
async def share_chat(session_id: str, user_id: str = Depends(get_current_user)):
    return await Router.share_chat(session_id, user_id)

@app.get("/api/sessions/{session_id}/info")
async def get_session_info(session_id: str, request: Request,
                            user_id: str = Depends(get_current_user)):
    """세션 기본 정보 + 참여자 목록 반환."""
    return await Loader.get_session_info(request.app.state.postgres, session_id)

@app.put("/api/sessions/{session_id}/title")
async def update_session_title(session_id: str, req: TitleUpdateRequest,
                                request: Request, user_id: str = Depends(get_current_user)):
    return await Router.update_session_title(session_id, req.title, user_id,
                                              request.app.state.postgres, request.app.state.redis)

@app.patch("/api/sessions/{session_id}/color")
async def update_session_color(session_id: str, req: SessionColorUpdateRequest,
                                request: Request, user_id: str = Depends(get_current_user)):
    return await Router.update_session_color(session_id, req.color, user_id,
                                              request.app.state.postgres)

@app.patch("/api/sessions/{session_id}/trip")
async def update_session_trip(session_id: str, req: SessionTripUpdateRequest,
                               request: Request, user_id: str = Depends(get_current_user)):
    return await Loader.move_session_to_trip(request.app.state.postgres, session_id, req.trip_id, user_id)


# ============================================================
# 메시지 API  →  Router  (로그인 필수)
# ============================================================

@app.get("/api/sessions/{session_id}/history")
async def get_chat_history(session_id: str, request: Request,
                            limit: int = 40, offset: int = 0,
                            user_id: str = Depends(get_current_user)):
    return await Router.get_chat_history(session_id, request.app.state.postgres,
                                         limit=limit, offset=offset)

@app.post("/api/sessions/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest, request: Request,
                       user_id: str = Depends(get_current_user)):
    return await Router.send_message(session_id, req.message, user_id,
                                      request.app.state.postgres, request.app.state.redis)

@app.post("/api/sessions/{session_id}/team-message")
async def send_team_message(session_id: str, req: MessageRequest, request: Request,
                             user_id: str = Depends(get_current_user)):
    """팀 채팅 전용 — AI 없이 저장 + SSE 브로드캐스트만."""
    from .router.router import Router
    return await Router._handle_team_message(session_id, user_id, req.message,
                                              request.app.state.postgres)

@app.post("/api/sessions/{session_id}/read")
async def mark_session_read(session_id: str, request: Request,
                             user_id: str = Depends(get_current_user)):
    """현재 세션 메시지를 읽음 처리 (last_read_at 갱신)."""
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    await request.app.state.postgres.execute({
        "action": "raw_sql",
        "sql": "UPDATE session_participants SET last_read_at = :now WHERE session_id = :sid AND user_id = :uid",
        "params": {"now": now, "sid": session_id, "uid": user_id},
    })
    return {"success": True}

@app.post("/api/sessions/{session_id}/typing")
async def send_typing(session_id: str, request: Request,
                      user_id: str = Depends(get_current_user)):
    """타이핑 중 이벤트를 같은 세션의 다른 구독자에게 SSE 브로드캐스트."""
    return await Router.broadcast_typing(session_id, user_id, request.app.state.postgres)

@app.get("/api/sessions/{session_id}/download")
async def download_chat(session_id: str, request: Request,
                         user_id: str = Depends(get_current_user)):
    return await Router.download_chat(session_id, request.app.state.postgres)


# ============================================================
# 파일 업로드  →  Router  (로그인 필수)
# ============================================================

@app.post("/api/sessions/{session_id}/files")
async def upload_files(session_id: str, request: Request,
                       files: List[UploadFile] = File(...),
                       user_id: str = Depends(get_current_user)):
    return await Router.upload_files(session_id, files, user_id, request.app.state.postgres)


# ============================================================
# 지도 API  →  Router  (로그인 필수)
# ============================================================

@app.post("/api/sessions/{session_id}/map/markers/add")
async def add_map_marker(session_id: str, req: MapMarkerAddRequest, request: Request,
                          user_id: str = Depends(get_current_user)):
    return await Router.add_map_marker(session_id, req.marker_id, req.lat, req.lng,
                                        req.title or "", user_id, request.app.state.redis)

@app.delete("/api/sessions/{session_id}/map/markers/{marker_id}")
async def delete_map_marker(session_id: str, marker_id: str, request: Request,
                             user_id: str = Depends(get_current_user)):
    return await Router.delete_map_marker(session_id, marker_id, user_id,
                                           request.app.state.redis)

@app.post("/api/sessions/{session_id}/map/markers")
async def save_map_markers(session_id: str, req: MapMarkersRequest, request: Request,
                            user_id: str = Depends(get_current_user)):
    return await Router.save_map_markers(session_id, req.markers, user_id,
                                          request.app.state.redis)

@app.get("/api/sessions/{session_id}/map/markers")
async def get_map_markers(session_id: str, request: Request,
                           user_id: str = Depends(get_current_user)):
    return await Router.get_map_markers(session_id, user_id, request.app.state.redis)

@app.post("/api/sessions/{session_id}/map/routes")
async def save_map_routes(session_id: str, req: MapRoutesRequest, request: Request,
                           user_id: str = Depends(get_current_user)):
    return await Router.save_map_routes(session_id, req.marker_ids, user_id,
                                         request.app.state.redis)

@app.get("/api/sessions/{session_id}/map/routes")
async def get_map_routes(session_id: str, request: Request,
                          user_id: str = Depends(get_current_user)):
    return await Router.get_map_routes(session_id, user_id, request.app.state.redis)


# ============================================================
# 여행 일정 API  →  Router  (로그인 필수)
# ============================================================

@app.put("/api/sessions/{session_id}/trip_range")
async def save_trip_range(session_id: str, req: TripRangeRequest, request: Request,
                           user_id: str = Depends(get_current_user)):
    return await Router.save_trip_range(session_id, req.ranges, user_id,
                                         request.app.state.redis)

@app.get("/api/sessions/{session_id}/trip_range")
async def get_trip_range(session_id: str, request: Request,
                          user_id: str = Depends(get_current_user)):
    return await Router.get_trip_range(session_id, user_id, request.app.state.redis)


# ============================================================
# 메모 / 플래너 API  →  Router  (로그인 필수)
# ============================================================

@app.put("/api/sessions/{session_id}/memo")
async def save_memo(session_id: str, date: str, req: MemoRequest, request: Request,
                    user_id: str = Depends(get_current_user)):
    return await Router.save_memo(session_id, date, req.memo, user_id, request.app.state.redis)

@app.get("/api/sessions/{session_id}/memo")
async def get_memo(session_id: str, date: str, request: Request,
                   user_id: str = Depends(get_current_user)):
    return await Router.get_memo(session_id, date, user_id, request.app.state.redis)

@app.put("/api/sessions/{session_id}/plan")
async def save_plan(session_id: str, date: str, req: PlanRequest, request: Request,
                    user_id: str = Depends(get_current_user)):
    return await Router.save_plan(session_id, date, req.plan, user_id, request.app.state.redis)

@app.get("/api/sessions/{session_id}/plan")
async def get_plan(session_id: str, date: str, request: Request,
                   user_id: str = Depends(get_current_user)):
    return await Router.get_plan(session_id, date, user_id, request.app.state.redis)

@app.get("/api/sessions/{session_id}/indicators")
async def get_indicators(session_id: str, year: int, month: int, request: Request,
                          user_id: str = Depends(get_current_user)):
    return await Router.get_indicators(session_id, year, month, user_id, request.app.state.redis)


# ============================================================
# 알림 API  →  Loader  (로그인 필수)
# ============================================================

@app.get("/api/notifications")
async def get_notifications(request: Request, user_id: str = Depends(get_current_user)):
    notifications = await Loader.get_notifications(request.app.state.postgres, user_id)
    return {"notifications": notifications}

@app.get("/api/notifications/stream")
async def notification_stream(user_id: str = Depends(get_current_user)):
    """사용자 전용 알림 SSE 스트림."""
    return await Router.subscribe_user_notifications(user_id)

@app.post("/api/notifications/{notification_id}/accept")
async def accept_notification(notification_id: str, request: Request,
                               user_id: str = Depends(get_current_user)):
    return await Loader.accept_session_invite(request.app.state.postgres, notification_id, user_id)

@app.post("/api/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, request: Request,
                                user_id: str = Depends(get_current_user)):
    return await Loader.dismiss_notification(request.app.state.postgres, notification_id, user_id)

@app.post("/api/notifications/clear-viewed")
async def clear_viewed_notifications(request: Request,
                                      user_id: str = Depends(get_current_user)):
    """읽음 처리된 알림을 UI에서만 숨김 (DB에는 is_hidden 플래그). DB는 유지."""
    return await Loader.clear_viewed_notifications(request.app.state.postgres, user_id)


# ============================================================
# Admin 전용 API  (user_id가 'MEM:admin'인 경우만 허용)
# ============================================================

async def _require_admin(request: Request, user_id: str = Depends(get_current_user)):
    from fastapi import HTTPException
    if user_id.endswith(':admin') or user_id == 'admin':
        return user_id
    result = await request.app.state.postgres.execute({
        "action": "raw_sql",
        "sql": "SELECT email FROM user_profile WHERE user_id = :uid",
        "params": {"uid": user_id},
    })
    email = (result.get("data") or [{}])[0].get("email", "")
    if email == "test@test.com":
        return user_id
    raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")

@app.get("/api/admin/users")
async def admin_get_users(request: Request, user_id: str = Depends(_require_admin)):
    """전체 사용자 목록 (admin 전용)."""
    result = await request.app.state.postgres.execute({
        "action": "raw_sql",
        "sql": """
            SELECT u.user_id, u.status, u.created_at,
                   up.nickname, up.email
            FROM users u
            LEFT JOIN user_profile up ON up.user_id = u.user_id
            WHERE u.status != 'deleted'
            ORDER BY u.created_at DESC
            LIMIT 200
        """,
        "params": {},
    })
    return {"users": result.get("data", [])}

@app.get("/api/admin/sessions")
async def admin_get_active_sessions(user_id: str = Depends(_require_admin)):
    """현재 메모리상 활성 세션 목록 (admin 전용)."""
    from .router.router import _active_sessions, _session_sse_queues
    return {
        "active_sessions": [
            {"session_id": sid, "sse_subscribers": len(_session_sse_queues.get(sid, []))}
            for sid in _active_sessions
        ]
    }


# ============================================================
# 정적 파일 / 뷰 라우터
# ============================================================

RESOURCE_DIR = os.path.join(BASE_DIR, "resource")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")
UPLOADS_DIR  = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.mount("/resource", StaticFiles(directory=RESOURCE_DIR), name="resource")
app.mount("/",         StaticFiles(directory=FRONTEND_DIR), name="frontend")
