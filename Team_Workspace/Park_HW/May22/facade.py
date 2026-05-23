"""
facade.py
TravelArchive 백엔드 진입점 — HTTP 라우팅만. 로직 없음.
"""

import json
import os
import secrets
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, "setting", ".env"))

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .execute_unit.auth import AuthUnit, get_current_user, get_optional_user
from .execute_unit.chat import ChatUnit
from .execute_unit.system import SystemUnit
from .execute_unit.user import UserUnit
from .execute_unit.widget import WidgetUnit
from .module.node.widget import WidgetPort2Adapter #
from .memory.cacher import Cacher
from .memory.loader import Loader


app = FastAPI(title="TravelArchive API", lifespan=Loader.lifespan)

_CORS_ORIGINS_RAW = os.getenv("CORS_ALLOW_ORIGINS", "")
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS if _CORS_ORIGINS else ["*"],
    allow_credentials=bool(_CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    plan_id: Optional[str] = None


class SessionColorUpdateRequest(BaseModel):
    color: str


class InviteRequest(BaseModel):
    user: str


class TitleUpdateRequest(BaseModel):
    title: str


class SessionTripUpdateRequest(BaseModel):
    trip_id: Optional[str] = None


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


class TripRangeRequest(BaseModel):
    ranges: List[Dict]

class TripPlanRequest(BaseModel):
    plan: List[List[Dict]]  # T_PN: 7일 × 10개 행렬


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


@app.post("/api/temp/{temp_session_id}/message")
async def send_temp_message(temp_session_id: str, req: TempMessageRequest):
    return await ChatUnit.send_temp_message(temp_session_id, req.message)


@app.post("/api/auth/signup")
async def signup(req: SignUpRequest, request: Request):
    return await AuthUnit.signup({"email": req.email, "password": req.password, "nickname": req.nickname}, request.app.state.manager)


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    return await AuthUnit.login(req.id, req.pw, request.app.state.manager)


@app.post("/api/auth/refresh")
async def refresh(req: RefreshRequest, request: Request):
    return await AuthUnit.refresh_token(req.refresh_token, request.app.state.manager)


@app.post("/api/auth/logout")
async def logout(req: LogoutRequest, request: Request, user_id: Optional[str] = Depends(get_optional_user)):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from .jwt_utils import verify_access_token
        try:
            payload = verify_access_token(auth_header[7:])
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                remaining = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
                await request.app.state.redis.set_str(f"auth:revoked:{jti}", "1", remaining)
        except Exception:
            pass
    await AuthUnit.logout(req.refresh_token, user_id, request.app.state.manager)
    return {"status": "success", "message": "로그아웃 되었습니다"}


@app.post("/api/auth/logout/all")
async def logout_all_devices(request: Request, user_id: str = Depends(get_current_user)):
    await AuthUnit.logout_all_devices(user_id, request.app.state.manager)
    return {"status": "success", "message": "모든 기기에서 로그아웃되었습니다"}


@app.get("/api/auth/kakao")
async def kakao_login_redirect():
    return RedirectResponse(AuthUnit.get_kakao_auth_url())


@app.get("/api/auth/kakao/callback")
async def kakao_callback(code: str, request: Request, state: Optional[str] = None):
    result = await AuthUnit.kakao_callback(code, request.app.state.redis, request.app.state.manager, state)
    if result.get("linked"):
        return RedirectResponse("/?kakao_linked=1")

    exchange_code = secrets.token_urlsafe(24)
    await request.app.state.redis.set_str(
        f"auth:kakao_code:{exchange_code}",
        json.dumps({
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "user_id": result.get("user_id", ""),
            "user_type": result["type"],
            "nickname": result.get("nickname", ""),
            "email": result.get("email", "") or "",
        }),
        60,
    )
    return RedirectResponse(f"/?code={exchange_code}")


@app.post("/api/auth/kakao/exchange")
async def kakao_exchange(request: Request):
    body = await request.json()
    exchange_code = body.get("code", "")
    if not exchange_code:
        raise HTTPException(status_code=400, detail="code가 없습니다")
    raw = await request.app.state.redis.get_str(f"auth:kakao_code:{exchange_code}")
    if not raw:
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 코드입니다")
    await request.app.state.redis.delete(f"auth:kakao_code:{exchange_code}")
    return json.loads(raw)


@app.get("/api/auth/kakao/link")
async def kakao_link_redirect(request: Request, user_id: str = Depends(get_current_user)):
    return RedirectResponse(await AuthUnit.initiate_kakao_link(user_id, request.app.state.redis))


@app.post("/api/auth/social/link/kakao")
async def link_kakao_account(request: Request, user_id: str = Depends(get_current_user)):
    url = await AuthUnit.initiate_kakao_link(user_id, request.app.state.redis)
    return {"status": "ok", "redirect_url": url}


@app.post("/api/auth/find")
async def find_account():
    return {"status": "not_implemented"}


@app.get("/api/auth/me")
async def get_my_info(request: Request, user_id: str = Depends(get_current_user)):
    return await AuthUnit.get_my_info(user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/flush")
async def flush_sessions(request: Request, user_id: str = Depends(get_current_user)):
    return SystemUnit.before_unload(user_id, request.app.state.manager)


@app.get("/api/account")
async def get_account_info(request: Request, user_id: str = Depends(get_optional_user)):
    return await UserUnit.get_account_info(request.app.state.redis, user_id)


@app.put("/api/user/profile")
async def save_user_profile(req: UserProfileRequest, request: Request, user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if not data:
        return {"status": "success"}
    return await UserUnit.save_profile(user_id, data, request.app.state.redis, request.app.state.manager)


@app.put("/api/user/style")
async def save_user_style(req: UserStyleRequest, request: Request, user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if not data:
        return {"status": "success"}
    return await UserUnit.save_style(user_id, data, request.app.state.redis, request.app.state.manager)


@app.put("/api/user/travel")
async def save_travel_preferences(req: UserTravelRequest, request: Request, user_id: str = Depends(get_current_user)):
    data = req.model_dump(exclude_none=True)
    if not data:
        return {"status": "success"}
    return await UserUnit.save_travel(user_id, data, request.app.state.redis, request.app.state.manager)


@app.delete("/api/user/account")
async def delete_account(request: Request, user_id: str = Depends(get_current_user)):
    return await UserUnit.delete_account(user_id, request.app.state.redis, request.app.state.manager)


@app.get("/api/context")
async def get_app_context(request: Request, user_id: str = Depends(get_optional_user)):
    return await SystemUnit.get_context(request.app.state.redis, user_id)


@app.get("/api/settings")
async def get_settings(request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.get_settings(request.app.state.redis, user_id, request.app.state.manager)


@app.post("/api/settings/update")
async def update_settings(settings: Dict[str, str], request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.update_settings(user_id, settings, request.app.state.redis)


@app.post("/api/theme")
async def save_theme_preference(req: ThemeRequest, request: Request, user_id: str = Depends(get_optional_user)):
    return await SystemUnit.save_theme(user_id, req.theme, request.app.state.redis)


@app.get("/api/help")
async def get_help_data():
    return SystemUnit.get_help()


@app.get("/api/trips")
async def get_trip_list(request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.get_trip_list(request.app.state.redis, request.app.state.manager, user_id)


@app.post("/api/trips")
async def create_trip(req: TripCreateRequest, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.create_trip(request.app.state.redis, request.app.state.manager, user_id, req.model_dump(exclude_none=True))


@app.put("/api/trips/{trip_id}")
async def update_trip(trip_id: str, req: TripUpdateRequest, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.update_trip(request.app.state.redis, request.app.state.manager, trip_id, user_id, req.model_dump(exclude_none=True))


@app.delete("/api/trips/{trip_id}")
async def delete_trip(trip_id: str, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.delete_trip(request.app.state.redis, request.app.state.manager, trip_id, user_id)



@app.get("/api/teams")
async def get_team_list(request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.get_team_list(request.app.state.redis, request.app.state.manager, user_id)


@app.post("/api/teams")
async def create_team(req: TeamCreateRequest, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.create_team(request.app.state.redis, request.app.state.manager, user_id, req.name)


@app.get("/api/teams/{team_id}/sessions")
async def get_team_sessions(team_id: str, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.get_team_sessions(request.app.state.redis, request.app.state.manager, team_id, user_id)


@app.get("/api/sessions")
async def get_session_list(request: Request, trip_id: Optional[str] = None, plan_id: Optional[str] = None, user_id: str = Depends(get_current_user)):
    return await SystemUnit.get_session_list(trip_id or plan_id, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions")
async def create_session(req: SessionCreateRequest, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.create_session(user_id, req.trip_id or req.plan_id, request.app.state.redis, request.app.state.manager)


async def _require_session_member(
    session_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> str:
    if not await Cacher.check_session_participant(
        session_id, user_id,
        request.app.state.redis,
        request.app.state.manager,
    ):
        raise HTTPException(status_code=403, detail="세션에 대한 접근 권한이 없습니다")
    return user_id


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.delete_session(session_id, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/leave")
async def leave_session(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.leave_session(session_id, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/convert-personal")
async def convert_to_personal(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.convert_to_personal(session_id, user_id, request.app.state.redis, request.app.state.manager)


@app.get("/api/users/search")
async def search_users(q: str, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.search_users(request.app.state.redis, request.app.state.manager, q, user_id)


@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.subscribe_session_events(session_id, user_id)


@app.post("/api/sessions/{session_id}/invite")
async def invite_user(session_id: str, req: InviteRequest, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.invite_user(session_id, req.user, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/share")
async def share_chat(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.share_chat(session_id, user_id)


@app.post("/api/sessions/{session_id}/open")
async def session_open(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.session_open(session_id, user_id, request.app.state.manager)


@app.post("/api/sessions/{session_id}/blur")
async def session_blur(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return SystemUnit.session_blur(session_id, user_id, request.app.state.manager)


@app.get("/api/sessions/{session_id}/info")
async def get_session_info(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.get_session_info(request.app.state.redis, request.app.state.manager, session_id)


@app.put("/api/sessions/{session_id}/title")
async def update_session_title(session_id: str, req: TitleUpdateRequest, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.update_session_title(session_id, req.title, user_id, request.app.state.redis, request.app.state.manager)


@app.patch("/api/sessions/{session_id}/color")
async def update_session_color(session_id: str, req: SessionColorUpdateRequest, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.update_session_color(session_id, req.color, user_id, request.app.state.redis, request.app.state.manager)


@app.patch("/api/sessions/{session_id}/trip")
async def update_session_trip(session_id: str, req: SessionTripUpdateRequest, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.move_session_to_trip(request.app.state.redis, request.app.state.manager, session_id, req.trip_id, user_id)


@app.get("/api/sessions/{session_id}/history")
async def get_chat_history(session_id: str, request: Request, limit: int = 40, offset: int = 0, user_id: str = Depends(_require_session_member)):
    limit = min(max(1, limit), 200)
    return await ChatUnit.get_chat_history(session_id, request.app.state.redis, request.app.state.manager, limit=limit, offset=offset)


@app.post("/api/sessions/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest, request: Request, user_id: str = Depends(_require_session_member)):
    return await ChatUnit.send_message(session_id, req.message, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/read")
async def mark_session_read(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.mark_session_read(request.app.state.redis, request.app.state.manager, session_id, user_id)


@app.get("/api/sessions/{session_id}/download")
async def download_chat(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return await SystemUnit.download_chat(session_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/files")
async def upload_files(session_id: str, request: Request, files: List[UploadFile] = File(...), user_id: str = Depends(_require_session_member)):
    return await SystemUnit.upload_files(session_id, files, user_id, request.app.state.redis, request.app.state.manager)


@app.post("/api/sessions/{session_id}/map/markers/add")
async def add_map_marker(session_id: str, req: MapMarkerAddRequest, request: Request, user_id: str = Depends(_require_session_member)):
    markers = await WidgetUnit.get_markers(session_id, request.app.state.redis)
    markers.append({"marker_id": req.marker_id, "lat": req.lat, "lng": req.lng, "title": req.title or ""})
    await WidgetUnit.set_markers(session_id, request.app.state.redis, markers)
    return {"success": True, "marker_id": req.marker_id}


@app.delete("/api/sessions/{session_id}/map/markers/{marker_id}")
async def delete_map_marker(session_id: str, marker_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    markers = [m for m in await WidgetUnit.get_markers(session_id, request.app.state.redis) if m.get("marker_id") != marker_id]
    await WidgetUnit.set_markers(session_id, request.app.state.redis, markers)
    return {"success": True}


@app.post("/api/sessions/{session_id}/map/markers")
async def save_map_markers(session_id: str, req: MapMarkersRequest, request: Request, user_id: str = Depends(_require_session_member)):
    await WidgetUnit.set_markers(session_id, request.app.state.redis, req.markers)
    return {"success": True}


@app.get("/api/sessions/{session_id}/map/markers")
async def get_map_markers(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return {"markers": await WidgetUnit.get_markers(session_id, request.app.state.redis)}


@app.post("/api/sessions/{session_id}/map/routes")
async def save_map_routes(session_id: str, req: MapRoutesRequest, request: Request, user_id: str = Depends(_require_session_member)):
    await WidgetUnit.set_routes(session_id, request.app.state.redis, req.marker_ids)
    return {"success": True}


@app.get("/api/sessions/{session_id}/map/routes")
async def get_map_routes(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return {"marker_ids": await WidgetUnit.get_routes(session_id, request.app.state.redis)}


@app.put("/api/sessions/{session_id}/trip_range")
async def save_trip_range(session_id: str, req: TripRangeRequest, request: Request, user_id: str = Depends(_require_session_member)):
    await WidgetUnit.set_trip_range(session_id, request.app.state.redis, req.ranges)
    return {"success": True}


@app.get("/api/sessions/{session_id}/trip_range")
async def get_trip_range(session_id: str, request: Request, user_id: str = Depends(_require_session_member)):
    return {"ranges": await WidgetUnit.get_trip_range(session_id, request.app.state.redis)}


@app.get("/api/sessions/{session_id}/trip_plan")
async def get_trip_plan(
    session_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    state = WidgetPort2Adapter.get_pc2_state(session_id)

    if not state or state.get("status") == "not_found":
        return {"plan": []}

    return {"plan": state.get("data", {}).get("t_pn", [])}

@app.put("/api/sessions/{session_id}/trip_plan")
async def save_trip_plan(
    session_id: str,
    req: TripPlanRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    return await WidgetPort2Adapter.update_t_pn(
        session_id=session_id,
        t_pn=req.plan,
        redis=request.app.state.redis,
    )


@app.get("/api/notifications")
async def get_notifications(request: Request, user_id: str = Depends(get_current_user)):
    notifications = await SystemUnit.get_notifications(user_id, request.app.state.redis, request.app.state.manager)
    return {"notifications": notifications}


@app.get("/api/notifications/stream")
async def notification_stream(user_id: str = Depends(get_current_user)):
    return await SystemUnit.subscribe_user_notifications(user_id)


@app.post("/api/notifications/{notification_id}/accept")
async def accept_notification(notification_id: str, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.accept_session_invite(request.app.state.redis, request.app.state.manager, notification_id, user_id)


@app.post("/api/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.dismiss_notification(request.app.state.redis, request.app.state.manager, notification_id, user_id)


@app.post("/api/notifications/clear-viewed")
async def clear_viewed_notifications(request: Request, user_id: str = Depends(get_current_user)):
    return await SystemUnit.clear_viewed_notifications(request.app.state.redis, request.app.state.manager, user_id)


async def _require_admin(request: Request, user_id: str = Depends(get_current_user)):
    return await AuthUnit.check_admin(user_id, request.app.state.manager)


@app.get("/api/admin/users")
async def admin_get_users(request: Request, user_id: str = Depends(_require_admin)):
    return {"users": await AuthUnit.admin_list_users(request.app.state.manager)}


@app.get("/api/admin/sessions")
async def admin_get_active_sessions(user_id: str = Depends(_require_admin)):
    return {"active_sessions": SystemUnit.get_active_session_info()}


RESOURCE_DIR = os.path.join(BASE_DIR, "resource")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
_UPLOADS_REAL = os.path.realpath(UPLOADS_DIR)

os.makedirs(UPLOADS_DIR, exist_ok=True)


@app.get("/api/files/{session_id}/{uploader_id}/{filename}")
async def serve_uploaded_file(
    session_id: str,
    uploader_id: str,
    filename: str,
    request: Request,
    user_id: str = Depends(_require_session_member),
):
    file_path = os.path.realpath(os.path.join(UPLOADS_DIR, session_id, uploader_id, filename))
    if not file_path.startswith(_UPLOADS_REAL + os.sep):
        raise HTTPException(status_code=400, detail="잘못된 경로입니다")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(file_path)


@app.get("/")
async def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


from fastapi.staticfiles import StaticFiles
app.mount("/resource", StaticFiles(directory=RESOURCE_DIR), name="resource")
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
