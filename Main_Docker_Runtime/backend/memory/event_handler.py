# [역할] 페이지/세션 생명주기 이벤트를 수신하여 Redis ↔ PostgreSQL 동기화를 처리하는
#        백그라운드 EventHandler 데몬.
import asyncio
from typing import Any, Coroutine

from .cacher import Cacher
from .constants import SESSION_TTL, USER_DATA_TTL
from .events import (
    AcceptInviteEvent,
    AccountDeleteEvent,
    AdminCheckEmailEvent,
    AdminListUsersEvent,
    BeforeUnloadEvent,
    CacheMissEvent,
    ClearNotifsEvent,
    CreateSessionEvent,
    CreateTeamEvent,
    CreateTripEvent,
    DeleteTripEvent,
    DismissNotifEvent,
    GetMiscTripEvent,
    GetMyInfoRequestEvent,
    GetSessionInfoEvent,
    GetSessionRoleEvent,
    GetUserByNicknameEvent,
    InviteUserEvent,
    KakaoAuthRequestEvent,
    LeaveAsMasterEvent,
    LeaveSessionEvent,
    LoadMessagesEvent,
    LoadNotificationsEvent,
    LoadSessionListEvent,
    LoadSessionParticipantsEvent,
    LoadTeamListEvent,
    LoadTeamSessionsEvent,
    LoadTripListEvent,
    LoadUserProfileEvent,
    LoadUserSessionTopicsEvent,
    LoginEvent,
    LoginRequestEvent,
    LogoutAllDevicesEvent,
    LogoutEvent,
    LogoutRequestEvent,
    MarkReadEvent,
    MoveSessionTripEvent,
    RefreshRequestEvent,
    RemoveNonMasterEvent,
    SaveMessageEvent,
    SaveNotificationEvent,
    SaveSettingsEvent,
    SearchUsersEvent,
    SessionBlurEvent,
    SessionOpenEvent,
    SessionTopicChangedEvent,
    SignupEvent,
    SignupRequestEvent,
    UpdateSessionRecordEvent,
    UpdateTripEvent,
    WidgetChangeEvent,
)
from .loader import Loader

SWEEP_INTERVAL = 60.0


class EventHandler:

    def __init__(self) -> None:
        self._priority_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._pg: Any = None
        self._redis: Any = None
        self._background_tasks: set[asyncio.Task] = set()  # GC 방지

    async def start(self, postgres: Any, redis: Any) -> None:
        self._pg = postgres
        self._redis = redis
        self._task = asyncio.create_task(self._loop(), name="MemoryManager")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._cancel_background_tasks()

    def emit(self, event: object, priority: bool = False) -> None:
        """fire-and-forget."""
        queue = self._priority_queue if priority else self._event_queue
        queue.put_nowait({"event": event, "done": None})
        if priority:
            self._event_queue.put_nowait({"event": None, "done": None})

    async def emit_and_wait(self, event: object, priority: bool = False) -> None:
        """완료 보장."""
        done = asyncio.Event()
        queue = self._priority_queue if priority else self._event_queue
        queue.put_nowait({"event": event, "done": done})
        if priority:
            self._event_queue.put_nowait({"event": None, "done": None})
        await done.wait()

    async def _loop(self) -> None:
        while True:
            try:
                try:
                    item = self._priority_queue.get_nowait()
                except asyncio.QueueEmpty:
                    item = await asyncio.wait_for(self._event_queue.get(), timeout=SWEEP_INTERVAL)
                done: asyncio.Event | None = item["done"]
                try:
                    await self._dispatch(item["event"])
                except Exception as e:
                    print(f"[EventHandler] 핸들러 오류: {e}")
                    ev = item["event"]
                    if hasattr(ev, "future") and not ev.future.done():
                        ev.future.set_exception(e)
                finally:
                    if done:
                        done.set()
            except asyncio.TimeoutError:
                try:
                    await self._idle_sweep()
                except Exception as e:
                    print(f"[EventHandler] idle_sweep 오류: {e}")
            except asyncio.CancelledError:
                break

    async def _dispatch(self, event: object) -> None:
        if event is None:
            return
        match event:
            case LoginEvent(): await self._on_login(event)
            case LogoutEvent(): await self._on_logout(event)
            case LogoutAllDevicesEvent(): await self._on_logout_all_devices(event)
            case SignupEvent(): await self._on_signup(event)
            case BeforeUnloadEvent(): await self._on_beforeunload(event)
            case SessionOpenEvent(): await self._on_session_open(event)
            case SessionBlurEvent(): await self._on_session_blur(event)
            case WidgetChangeEvent(): await self._on_widget_change(event)
            case CacheMissEvent(): await self._on_cache_miss(event)
            case AccountDeleteEvent(): await self._on_account_delete(event)
            case SaveSettingsEvent(): await self._on_save_settings(event)
            case LoginRequestEvent(): await self._on_login_request(event)
            case LogoutRequestEvent(): await self._on_logout_request(event)
            case SignupRequestEvent(): await self._on_signup_request(event)
            case RefreshRequestEvent(): await self._on_refresh_request(event)
            case GetMyInfoRequestEvent(): await self._on_get_my_info_request(event)
            case AdminCheckEmailEvent(): await self._on_admin_check_email(event)
            case AdminListUsersEvent(): await self._on_admin_list_users(event)
            case KakaoAuthRequestEvent(): await self._on_kakao_auth_request(event)
            case LoadUserProfileEvent(): await self._on_load_user_profile(event)
            case LoadSessionListEvent(): await self._on_load_session_list(event)
            case LoadTripListEvent(): await self._on_load_trip_list(event)
            case LoadTeamListEvent(): await self._on_load_team_list(event)
            case LoadTeamSessionsEvent(): await self._on_load_team_sessions(event)
            case LoadNotificationsEvent(): await self._on_load_notifications(event)
            case LoadMessagesEvent(): await self._on_load_messages(event)
            case LoadSessionParticipantsEvent(): await self._on_load_session_participants(event)
            case GetSessionInfoEvent(): await self._on_get_session_info(event)
            case SearchUsersEvent(): await self._on_search_users(event)
            case GetMiscTripEvent(): await self._on_get_misc_trip(event)
            case GetSessionRoleEvent(): await self._on_get_session_role(event)
            case GetUserByNicknameEvent(): await self._on_get_user_by_nickname(event)
            case SaveMessageEvent(): await self._on_save_message(event)
            case SaveNotificationEvent(): await self._on_save_notification(event)
            case CreateSessionEvent(): await self._on_create_session(event)
            case LeaveSessionEvent(): await self._on_leave_session(event)
            case LeaveAsMasterEvent(): await self._on_leave_as_master(event)
            case UpdateSessionRecordEvent(): await self._on_update_session_record(event)
            case RemoveNonMasterEvent(): await self._on_remove_non_master(event)
            case InviteUserEvent(): await self._on_invite_user(event)
            case MoveSessionTripEvent(): await self._on_move_session_trip(event)
            case MarkReadEvent(): await self._on_mark_read(event)
            case CreateTripEvent(): await self._on_create_trip(event)
            case UpdateTripEvent(): await self._on_update_trip(event)
            case DeleteTripEvent(): await self._on_delete_trip(event)
            case CreateTeamEvent(): await self._on_create_team(event)
            case AcceptInviteEvent(): await self._on_accept_invite(event)
            case DismissNotifEvent(): await self._on_dismiss_notif(event)
            case ClearNotifsEvent(): await self._on_clear_notifs(event)
            case SessionTopicChangedEvent(): await self._on_session_topic_changed(event)
            case LoadUserSessionTopicsEvent(): await self._on_load_user_session_topics(event)
            case _: print(f"[EventHandler] 알 수 없는 이벤트: {type(event)}")

    async def _on_login(self, e: LoginEvent) -> None:
        await Loader.load_user_to_redis(e.user_id, self._pg, self._redis)

    async def _on_logout(self, e: LogoutEvent) -> None:
        await Loader.flush_user_data(e.user_id, self._pg, self._redis)
        from ..execute_unit.chat.chat_flush_service import FlushService
        await FlushService.flush_user_sessions(e.user_id, self._redis, self)
        await Cacher.delete_user_data(e.user_id, self._redis)

    async def _on_logout_all_devices(self, e: LogoutAllDevicesEvent) -> None:
        try:
            await Loader.logout_all_devices(self._redis, e.user_id)
            e.future.set_result(None)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_signup(self, e: SignupEvent) -> None:
        await Cacher.save_user_profile(e.user_id, {}, self._redis)

    async def _on_beforeunload(self, e: BeforeUnloadEvent) -> None:
        try:
            async with asyncio.timeout(5.0):
                await Loader.flush_user_data(e.user_id, self._pg, self._redis, clear=False)
                from ..execute_unit.chat.chat_flush_service import FlushService
                await FlushService.flush_user_sessions(e.user_id, self._redis, self)
        except TimeoutError:
            print(f"[EventHandler] beforeunload flush 타임아웃: {e.user_id}")

    async def _on_session_open(self, e: SessionOpenEvent) -> None:
        if not await Cacher.get_session_meta(e.session_id, self._redis):
            await Loader.load_session_to_redis(e.session_id, self._pg, self._redis)
        profile = await Cacher.get_user_profile(e.user_id, self._redis)
        if not profile.get("nickname"):
            await Loader.load_user_to_redis(e.user_id, self._pg, self._redis)
        await Cacher.mark_active(e.user_id, e.session_id, self._redis)

    async def _on_session_blur(self, e: SessionBlurEvent) -> None:
        await Loader.flush_dirty_widgets(e.session_id, self._pg, self._redis)

    async def _on_widget_change(self, e: WidgetChangeEvent) -> None:
        await Cacher.mark_dirty_widget(e.session_id, e.widget_type, self._redis)

    async def _on_cache_miss(self, e: CacheMissEvent) -> None:
        if e.resource == "user_profile" and e.user_id:
            profile = await Cacher.get_user_profile(e.user_id, self._redis)
            if not profile.get("nickname"):
                await Loader.load_user_to_redis(e.user_id, self._pg, self._redis)
        elif e.resource == "session_meta" and e.session_id:
            await Loader.load_session_to_redis(e.session_id, self._pg, self._redis)

    async def _on_account_delete(self, e: AccountDeleteEvent) -> None:
        if await Cacher.is_account_deleted(e.user_id, self._redis):
            await Loader.mark_user_deleted(self._pg, e.user_id)
        await Cacher.delete_user_data(e.user_id, self._redis)

    async def _on_login_request(self, e: LoginRequestEvent) -> None:
        try:
            result = await Loader.login(self._pg, self._redis, e.email, e.password)
            if result.get("user_id"):
                # load_user_to_redis를 future resolve 전에 완료: /api/context 레이스 방지
                await Loader.load_user_to_redis(result["user_id"], self._pg, self._redis)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_logout_request(self, e: LogoutRequestEvent) -> None:
        try:
            if e.user_id:
                await Loader.flush_user_data(e.user_id, self._pg, self._redis)
                from ..execute_unit.chat.chat_flush_service import FlushService
                await FlushService.flush_user_sessions(e.user_id, self._redis, self)
                await Cacher.delete_user_data(e.user_id, self._redis)
            await Loader.logout(self._pg, self._redis, e.refresh_token)
            e.future.set_result(None)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_signup_request(self, e: SignupRequestEvent) -> None:
        try:
            result = await Loader.signup(self._pg, e.data)
            if result.get("user_id"):
                self.emit(SignupEvent(user_id=result["user_id"]))
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_refresh_request(self, e: RefreshRequestEvent) -> None:
        try:
            e.future.set_result(await Loader.refresh_token(self._redis, e.refresh_token))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_get_my_info_request(self, e: GetMyInfoRequestEvent) -> None:
        try:
            e.future.set_result(await Loader.get_my_info(self._pg, e.user_id))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_admin_check_email(self, e: AdminCheckEmailEvent) -> None:
        try: e.future.set_result(await Loader.admin_get_email(self._pg, e.user_id))
        except Exception as ex: e.future.set_exception(ex)

    async def _on_admin_list_users(self, e: AdminListUsersEvent) -> None:
        try: e.future.set_result(await Loader.admin_list_users(self._pg))
        except Exception as ex: e.future.set_exception(ex)

    async def _on_kakao_auth_request(self, e: KakaoAuthRequestEvent) -> None:
        try:
            result = await Loader.kakao_oauth_lookup_or_create(
                self._pg,
                provider_uid=e.provider_uid,
                nickname=e.nickname,
                email=e.email,
                profile_img_url=e.profile_img_url,
                state=e.state,
                redis=e.redis,
            )
            if not result.get("linked") and result.get("user_id"):
                await Loader.load_user_to_redis(result["user_id"], self._pg, self._redis)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_save_settings(self, e: SaveSettingsEvent) -> None:
        try:
            style  = await Cacher.get_user_style(e.user_id, self._redis)
            travel = await Cacher.get_user_travel(e.user_id, self._redis)
            # PG 동기화만 수행, Redis는 유지 (분석 background에서 prev_analysis 필요)
            await Loader.flush_user_data(e.user_id, self._pg, self._redis, clear=False)
            if style or travel:
                self._spawn(self._run_user_analyze_settings(e.user_id, style, travel))
        except Exception as ex:
            print(f"[EventHandler] save_settings flush 실패 {e.user_id}: {ex}")

    async def _on_session_topic_changed(self, e: SessionTopicChangedEvent) -> None:
        self._spawn(self._run_user_analyze_topic(e))

    async def _on_load_user_session_topics(self, e: LoadUserSessionTopicsEvent) -> None:
        try:
            topics = await Loader.get_user_session_topics(self._pg, e.user_id, e.exclude_session_id)
            e.future.set_result(topics)
        except Exception as ex:
            e.future.set_exception(ex)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        """백그라운드 태스크 생성 (GC 방지 포함)."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        if exc := task.exception():
            print(f"[EventHandler] background task 오류: {exc}")

    async def _cancel_background_tasks(self) -> None:
        if not self._background_tasks:
            return
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _run_user_analyze_topic(self, e: SessionTopicChangedEvent) -> None:
        try:
            from ..execute_unit.user.user_analyze import UserAnalyze
            await UserAnalyze.run_on_topic_change(
                user_id=e.user_id,
                session_id=e.session_id,
                prev_topic=e.prev_topic,
                new_topic=e.new_topic,
                redis=self._redis,
                manager=self,
            )
        except Exception as ex:
            print(f"[EventHandler] user_analyze(topic) 오류: {ex}")

    async def _run_user_analyze_settings(self, user_id: str, style: dict, travel: dict) -> None:
        try:
            from ..execute_unit.user.user_analyze import UserAnalyze
            await UserAnalyze.run_on_settings_change(
                user_id=user_id,
                style=style,
                travel=travel,
                redis=self._redis,
                manager=self,
            )
        except Exception as ex:
            print(f"[EventHandler] user_analyze(settings) 오류: {ex}")

    async def _on_load_user_profile(self, e: LoadUserProfileEvent) -> None:
        try:
            data = await Loader.fetch_user_profile(e.user_id, self._pg)
            if data:
                await Cacher.save_user_profile(e.user_id, data, self._redis)
            e.future.set_result(data)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_session_list(self, e: LoadSessionListEvent) -> None:
        try:
            sessions = await Loader.get_session_list(self._pg, e.user_id, e.trip_id)
            await self._cache_json(f"user:{e.user_id}:sessions:{e.trip_id or 'all'}", sessions, SESSION_TTL)
            e.future.set_result(sessions)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_trip_list(self, e: LoadTripListEvent) -> None:
        try:
            trips = await Loader.get_trip_list(self._pg, e.user_id)
            await self._cache_json(f"user:{e.user_id}:trips", trips, USER_DATA_TTL)
            e.future.set_result(trips)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_team_list(self, e: LoadTeamListEvent) -> None:
        try:
            teams = await Loader.get_user_teams(self._pg, e.user_id)
            await self._cache_json(f"user:{e.user_id}:teams", teams, USER_DATA_TTL)
            e.future.set_result(teams)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_team_sessions(self, e: LoadTeamSessionsEvent) -> None:
        try:
            sessions = await Loader.get_team_sessions(self._pg, e.team_id)
            await self._cache_json(f"team:{e.team_id}:sessions", sessions, SESSION_TTL)
            e.future.set_result(sessions)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_notifications(self, e: LoadNotificationsEvent) -> None:
        try:
            notifs = await Loader.get_notifications(self._pg, e.user_id)
            await self._cache_json(f"user:{e.user_id}:notifications", notifs, USER_DATA_TTL)
            e.future.set_result(notifs or [])
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_messages(self, e: LoadMessagesEvent) -> None:
        try:
            e.future.set_result(await Loader.get_conversation_history(self._pg, e.session_id, e.limit, e.offset))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_load_session_participants(self, e: LoadSessionParticipantsEvent) -> None:
        try:
            participants = await Loader.get_session_participants(self._pg, e.session_id)
            await self._cache_json(f"session:{e.session_id}:participants", participants, SESSION_TTL)
            e.future.set_result(participants)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_get_session_info(self, e: GetSessionInfoEvent) -> None:
        try:
            e.future.set_result(await Loader.get_session_info(self._pg, e.session_id))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_search_users(self, e: SearchUsersEvent) -> None:
        try:
            e.future.set_result(await Loader.search_users(self._pg, e.q, e.user_id))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_get_misc_trip(self, e: GetMiscTripEvent) -> None:
        try:
            e.future.set_result(await Loader.ensure_misc_trip(self._pg, e.user_id))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_get_session_role(self, e: GetSessionRoleEvent) -> None:
        try:
            e.future.set_result(await Loader.get_session_role(self._pg, e.session_id, e.user_id))
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_get_user_by_nickname(self, e: GetUserByNicknameEvent) -> None:
        try:
            user_id = await Loader.get_user_id_by_nickname(self._pg, e.nickname)
            if user_id:
                await self._redis.set_str(f"nick:{e.nickname}:user_id", user_id, USER_DATA_TTL)
            e.future.set_result(user_id)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_save_message(self, e: SaveMessageEvent) -> None:
        try:
            await Loader.save_conversation_message(self._pg, e.msg_data)
        except Exception as ex:
            print(f"[EventHandler] save_message 실패 {e.session_id}: {ex}")

    async def _on_save_notification(self, e: SaveNotificationEvent) -> None:
        try:
            await Loader.save_notification_record(self._pg, e.notif_data)
        except Exception as ex:
            print(f"[EventHandler] save_notification 실패 {e.user_id}: {ex}")

    async def _on_create_session(self, e: CreateSessionEvent) -> None:
        try:
            await Loader.create_session_record(self._pg, e.session_id, e.user_id, e.data)
            e.future.set_result(None)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_leave_session(self, e: LeaveSessionEvent) -> None:
        try:
            await Loader.leave_session(self._pg, e.session_id, e.user_id)
        except Exception as ex:
            print(f"[EventHandler] leave_session 실패 {e.session_id}: {ex}")

    async def _on_leave_as_master(self, e: LeaveAsMasterEvent) -> None:
        try:
            result = await Loader.leave_as_master(self._pg, e.session_id, e.user_id)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_update_session_record(self, e: UpdateSessionRecordEvent) -> None:
        try:
            await Loader.update_session_record(self._pg, e.session_id, e.data)
        except Exception as ex:
            print(f"[EventHandler] update_session_record 실패 {e.session_id}: {ex}")

    async def _on_remove_non_master(self, e: RemoveNonMasterEvent) -> None:
        try:
            await Loader.remove_non_master_participants(self._pg, e.session_id)
            await self._redis.delete(f"session:{e.session_id}:participants")
        except Exception as ex:
            print(f"[EventHandler] remove_non_master 실패 {e.session_id}: {ex}")

    async def _on_invite_user(self, e: InviteUserEvent) -> None:
        try:
            result = await Loader.invite_to_session(self._pg, e.session_id, e.inviter_id, e.invitee)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_move_session_trip(self, e: MoveSessionTripEvent) -> None:
        try:
            result = await Loader.move_session_to_trip(self._pg, e.session_id, e.trip_id, e.user_id)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_mark_read(self, e: MarkReadEvent) -> None:
        try:
            await Loader.mark_session_read(self._pg, e.session_id, e.user_id)
        except Exception as ex:
            print(f"[EventHandler] mark_read 실패 {e.session_id}: {ex}")

    async def _on_create_trip(self, e: CreateTripEvent) -> None:
        try:
            result = await Loader.create_trip(self._pg, e.user_id, e.data)
            await self._redis.delete(f"user:{e.user_id}:trips")
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_update_trip(self, e: UpdateTripEvent) -> None:
        try:
            result = await Loader.update_trip(self._pg, e.trip_id, e.user_id, e.data)
            await self._redis.delete(f"user:{e.user_id}:trips")
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_delete_trip(self, e: DeleteTripEvent) -> None:
        try:
            result = await Loader.delete_trip(self._pg, e.trip_id, e.user_id)
            await self._redis.delete(f"user:{e.user_id}:trips")
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_create_team(self, e: CreateTeamEvent) -> None:
        try:
            result = await Loader.create_team(self._pg, e.user_id, e.name)
            await self._redis.delete(f"user:{e.user_id}:teams")
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_accept_invite(self, e: AcceptInviteEvent) -> None:
        try:
            result = await Loader.accept_session_invite(self._pg, e.notification_id, e.user_id)
            await self._redis.delete(f"user:{e.user_id}:notifications")
            # Redis-first: 수락한 세션을 본인 Redis 목록에 명시 add
            session_id = result.get("session_id") if isinstance(result, dict) else None
            if session_id:
                rows = await Loader.get_session_list(self._pg, e.user_id, None)
                entry = next((s for s in rows if s.get("session_id") == session_id), None)
                if entry:
                    await Cacher.session_list_add(e.user_id, entry, self._redis)
            e.future.set_result(result)
        except Exception as ex:
            e.future.set_exception(ex)

    async def _on_dismiss_notif(self, e: DismissNotifEvent) -> None:
        try:
            await Loader.dismiss_notification(self._pg, e.notification_id, e.user_id)
            await self._redis.delete(f"user:{e.user_id}:notifications")
        except Exception as ex:
            print(f"[EventHandler] dismiss_notif 실패 {e.notification_id}: {ex}")

    async def _on_clear_notifs(self, e: ClearNotifsEvent) -> None:
        try:
            await Loader.clear_viewed_notifications(self._pg, e.user_id)
            await self._redis.delete(f"user:{e.user_id}:notifications")
        except Exception as ex:
            print(f"[EventHandler] clear_notifs 실패 {e.user_id}: {ex}")

    async def _cache_json(self, key: str, value: Any, ttl: int) -> None:
        if value is not None:
            await self._redis.set_json(key, value, ttl)

    async def _idle_sweep(self) -> None:
        keys = await self._redis.scan("session:*:dirty_widgets")
        for key in keys:
            parts = key.split(":")
            if len(parts) == 3:
                try:
                    await Loader.flush_dirty_widgets(parts[1], self._pg, self._redis)
                except Exception as e:
                    print(f"[EventHandler] sweep flush 실패 {parts[1]}: {e}")
