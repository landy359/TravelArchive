from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean, Column, Date, Numeric, ForeignKey, Integer,
    String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# ══════════════════════════════════════════════════════════════
# 1. 사용자 도메인 (Users & Teams)
# ══════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    user_id    = Column(String(40), primary_key=True)
    user_type  = Column(String(10), nullable=False)          # MEM / GST / KKO
    status     = Column(String(20), nullable=False, server_default="active")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class UserSecurity(Base):
    """로컬(MEM) 계정 전용. SNS 계정은 이 행이 없음."""
    __tablename__ = "user_security"

    user_id          = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    password_hash    = Column(String(255), nullable=False)
    login_fail_count = Column(Integer, nullable=False, server_default="0")
    locked_until     = Column(TIMESTAMP(timezone=True), nullable=True)
    last_login_at    = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class UserOAuth(Base):
    """카카오 SNS 연동. provider 확장 가능 구조이나 현재 kakao만 사용."""
    __tablename__ = "user_oauth"

    oauth_id     = Column(String(50), primary_key=True)
    user_id      = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    provider     = Column(String(20), nullable=False, server_default="kakao")
    provider_uid = Column(String(255), nullable=False)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("provider", "provider_uid", name="uq_oauth_provider_uid"),
    )


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id         = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    email           = Column(String(255), nullable=True, unique=True)
    phone           = Column(String(20),  nullable=True)
    name            = Column(String(50),  nullable=True)
    nickname        = Column(String(50),  nullable=True)
    birthday        = Column(Date,        nullable=True)
    profile_img_url = Column(Text,        nullable=True)
    bio             = Column(Text,        nullable=True)
    extra_contacts  = Column(JSONB,       nullable=True)
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id             = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    travel_style        = Column(String(50), nullable=True)
    transport_type      = Column(JSONB,      nullable=True)
    preferred_food      = Column(JSONB,      nullable=True)
    schedule_density    = Column(String(20), nullable=True)
    companion_type      = Column(String(20), nullable=True)
    personalized_topics = Column(JSONB,      nullable=True)
    ui_settings         = Column(JSONB,      nullable=True)   # UI 전용: 투명도/테마/폰트/알림
    style               = Column(JSONB,      nullable=True)   # AI 스타일·말투 설정
    travel              = Column(JSONB,      nullable=True)   # 여행 스타일 설정
    updated_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Team(Base):
    __tablename__ = "teams"

    team_id     = Column(String(50), primary_key=True)
    created_by  = Column(String(40), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    name        = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id   = Column(String(50), ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True)
    user_id   = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    role      = Column(String(20), nullable=False, server_default="member")  # owner / admin / member
    joined_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# ══════════════════════════════════════════════════════════════
# 2. 장소 & 날씨 도메인 (Places & Weather)
# ══════════════════════════════════════════════════════════════

class Place(Base):
    __tablename__ = "places"

    place_id        = Column(String(50),  primary_key=True)
    external_id     = Column(String(100), nullable=True)
    external_source = Column(String(30),  nullable=True)   # kakao / google / manual / crawl
    name            = Column(String(255), nullable=False)
    place_type      = Column(String(20),  nullable=False)  # spot / restaurant / cafe / hotel
    description     = Column(Text,        nullable=True)
    address         = Column(String(255), nullable=True)
    geom            = Column(Geometry("POINT", srid=4326), nullable=True)
    region_code     = Column(String(50),  nullable=True)
    contact_info    = Column(String(100), nullable=True)
    opening_hours   = Column(JSONB,       nullable=True)
    price_range     = Column(String(20),  nullable=True)   # low / mid / high
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("external_source", "external_id", name="uq_place_external"),
    )


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"

    weather_id     = Column(String(50), primary_key=True)
    region_code    = Column(String(50), nullable=False)
    target_date    = Column(Date,       nullable=False)
    condition_code = Column(Integer,    nullable=False)
    temp_min       = Column(Numeric(4, 1), nullable=True)
    temp_max       = Column(Numeric(4, 1), nullable=True)
    rain_prob      = Column(Integer,    nullable=True)
    wind_speed     = Column(Numeric(4, 1), nullable=True)
    fetched_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("region_code", "target_date", name="uq_weather_region_date"),
    )


# ══════════════════════════════════════════════════════════════
# 3. 여행 도메인 (Trips & Itineraries)
# ══════════════════════════════════════════════════════════════

class Trip(Base):
    __tablename__ = "trips"

    trip_id         = Column(String(50),   primary_key=True)
    team_id         = Column(String(50),   ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    created_by      = Column(String(40),   ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    title           = Column(String(255),  nullable=False)
    color           = Column(String(20),   nullable=True)   # UI 색상 표시용 hex (#FF6B6B 등)
    destination     = Column(String(100),  nullable=True)
    start_date      = Column(Date,         nullable=True)
    end_date        = Column(Date,         nullable=True)
    expected_budget = Column(Numeric(15, 2), nullable=True)
    cover_img_url   = Column(Text,         nullable=True)
    is_misc         = Column(Boolean,      nullable=False, server_default="false")  # '기타' 기본 trip
    status          = Column(String(20),   nullable=False, server_default="planning")
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class TripDay(Base):
    __tablename__ = "trip_days"

    day_id      = Column(String(50), primary_key=True)
    trip_id     = Column(String(50), ForeignKey("trips.trip_id", ondelete="CASCADE"), nullable=False)
    day_number  = Column(Integer,    nullable=False)
    target_date = Column(Date,       nullable=False)
    weather_id  = Column(String(50), ForeignKey("weather_snapshots.weather_id", ondelete="SET NULL"), nullable=True)
    daily_memo  = Column(Text,       nullable=True)

    __table_args__ = (
        UniqueConstraint("trip_id", "day_number",  name="uq_tripday_number"),
        UniqueConstraint("trip_id", "target_date", name="uq_tripday_date"),
    )


# ══════════════════════════════════════════════════════════════
# 4. 세션 도메인 (Sessions, Chat & Proposals)
# ══════════════════════════════════════════════════════════════

class Session(Base):
    __tablename__ = "sessions"

    session_id      = Column(String(50),  primary_key=True)
    trip_id         = Column(String(50),  ForeignKey("trips.trip_id", ondelete="SET NULL"), nullable=True)
    created_by      = Column(String(40),  ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    title           = Column(String(255), nullable=True)
    color           = Column(String(20),  nullable=True)
    is_manual_title = Column(Boolean,     nullable=False, server_default="false")
    topic           = Column(Text,        nullable=True)
    context_summary = Column(Text,        nullable=True)
    is_active       = Column(Boolean,     nullable=False, server_default="true")
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    session_id   = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)
    user_id      = Column(String(40), ForeignKey("users.user_id",    ondelete="CASCADE"), primary_key=True)
    role         = Column(String(20), nullable=False, server_default="viewer")  # master / participant / viewer
    joined_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_read_at = Column(TIMESTAMP(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    message_id   = Column(String(50), primary_key=True)
    session_id   = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    sender_id    = Column(String(40), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    sender_type  = Column(String(20), nullable=False)   # user / ai / system — DEFAULT 없음, 반드시 명시
    message_type = Column(String(20), nullable=False, server_default="text")  # text / file / proposal
    content      = Column(Text,       nullable=False)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Proposal(Base):
    __tablename__ = "proposals"

    proposal_id     = Column(String(50), primary_key=True)
    message_id      = Column(String(50), ForeignKey("conversations.message_id", ondelete="CASCADE"), nullable=False)
    target_day_id   = Column(String(50), ForeignKey("trip_days.day_id", ondelete="CASCADE"), nullable=False)
    place_id        = Column(String(50), ForeignKey("places.place_id", ondelete="RESTRICT"), nullable=False)
    suggested_order = Column(Integer,    nullable=True)
    suggested_time  = Column(Time,       nullable=True)
    status          = Column(String(20), nullable=False, server_default="pending")  # pending / accepted / rejected
    resolved_by     = Column(String(40), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    resolved_at     = Column(TIMESTAMP(timezone=True), nullable=True)


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    item_id        = Column(String(50), primary_key=True)
    day_id         = Column(String(50), ForeignKey("trip_days.day_id", ondelete="CASCADE"), nullable=False)
    place_id       = Column(String(50), ForeignKey("places.place_id", ondelete="SET NULL"), nullable=True)
    proposal_id    = Column(String(50), ForeignKey("proposals.proposal_id", ondelete="SET NULL"), nullable=True)
    visit_order    = Column(Integer,    nullable=False)
    start_time     = Column(Time,       nullable=True)
    end_time       = Column(Time,       nullable=True)
    transport_mode = Column(String(20), nullable=True)
    map_route_data = Column(JSONB,      nullable=True)
    estimated_cost = Column(Numeric(10, 2), nullable=True)
    memo           = Column(Text,       nullable=True)
    status         = Column(String(20), nullable=False, server_default="proposed")  # proposed / confirmed


class SessionMarker(Base):
    __tablename__ = "session_markers"

    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)
    place_id   = Column(String(50), ForeignKey("places.place_id",    ondelete="CASCADE"), primary_key=True)
    marker_id  = Column(String(50), nullable=False)
    created_by = Column(String(10), nullable=False, server_default="user")  # user / ai
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("session_id", "marker_id", name="uq_marker_per_session"),
    )


class SessionFile(Base):
    __tablename__ = "session_files"

    file_id     = Column(String(50), primary_key=True)
    session_id  = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    message_id  = Column(String(50), ForeignKey("conversations.message_id", ondelete="SET NULL"), nullable=True)
    uploader_id = Column(String(40), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    file_url    = Column(Text,        nullable=False)
    file_name   = Column(String(255), nullable=False)
    file_type   = Column(String(50),  nullable=False)
    uploaded_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# ══════════════════════════════════════════════════════════════
# 5. 알림 도메인 (Notifications)
# ══════════════════════════════════════════════════════════════

class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(String(50), primary_key=True)
    user_id         = Column(String(40), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    type            = Column(String(40), nullable=False)
    reference_type  = Column(String(20), nullable=False)
    reference_id    = Column(String(50), nullable=False)
    message         = Column(Text,       nullable=False)
    is_read         = Column(Boolean,    nullable=False, server_default="false")
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
