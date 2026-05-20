"""initial schema — full rebuild

Revision ID: 001
Revises:
Create Date: 2026-04-29

구버전 테이블(auth_tokens, refresh_tokens, test_*, user_preference 등)을 모두 제거하고
확정된 스키마의 19개 테이블을 새로 생성합니다.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────
    # 0. 구버전 테이블 제거 (FK 순서 무시하고 CASCADE로 일괄 삭제)
    # ──────────────────────────────────────────────────────────
    old_tables = [
        "refresh_tokens", "auth_tokens",
        "test_comment", "test_article",
        "user_oauth", "user_preference",
        "user_security", "user_profile", "users",
    ]
    for t in old_tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    # ──────────────────────────────────────────────────────────
    # 1. users
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id",    sa.String(40),  nullable=False),
        sa.Column("user_type",  sa.String(10),  nullable=False),
        sa.Column("status",     sa.String(20),  nullable=False, server_default="active"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 2. user_security
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "user_security",
        sa.Column("user_id",          sa.String(40),  nullable=False),
        sa.Column("password_hash",    sa.String(255), nullable=False),
        sa.Column("login_fail_count", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("locked_until",     postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_login_at",    postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at",       postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 3. user_oauth
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "user_oauth",
        sa.Column("oauth_id",     sa.String(50),  nullable=False),
        sa.Column("user_id",      sa.String(40),  nullable=False),
        sa.Column("provider",     sa.String(20),  nullable=False, server_default="kakao"),
        sa.Column("provider_uid", sa.String(255), nullable=False),
        sa.Column("created_at",   postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("oauth_id"),
        sa.UniqueConstraint("provider", "provider_uid", name="uq_oauth_provider_uid"),
    )

    # ──────────────────────────────────────────────────────────
    # 4. user_profile
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "user_profile",
        sa.Column("user_id",         sa.String(40),  nullable=False),
        sa.Column("email",           sa.String(255), nullable=True),
        sa.Column("phone",           sa.String(20),  nullable=True),
        sa.Column("name",            sa.String(50),  nullable=True),
        sa.Column("nickname",        sa.String(50),  nullable=True),
        sa.Column("birthday",        sa.Date(),      nullable=True),
        sa.Column("profile_img_url", sa.Text(),      nullable=True),
        sa.Column("updated_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email", name="uq_user_profile_email"),
    )

    # ──────────────────────────────────────────────────────────
    # 5. user_preferences
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "user_preferences",
        sa.Column("user_id",             sa.String(40), nullable=False),
        sa.Column("travel_style",        sa.String(50), nullable=True),
        sa.Column("transport_type",      postgresql.JSONB(), nullable=True),
        sa.Column("preferred_food",      postgresql.JSONB(), nullable=True),
        sa.Column("schedule_density",    sa.String(20), nullable=True),
        sa.Column("companion_type",      sa.String(20), nullable=True),
        sa.Column("personalized_topics", postgresql.JSONB(), nullable=True),
        sa.Column("ui_settings",         postgresql.JSONB(), nullable=True),
        sa.Column("updated_at",          postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 6. teams
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "teams",
        sa.Column("team_id",     sa.String(50),  nullable=False),
        sa.Column("created_by",  sa.String(40),  nullable=False),
        sa.Column("name",        sa.String(100), nullable=False),
        sa.Column("description", sa.Text(),      nullable=True),
        sa.Column("created_at",  postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("team_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 7. team_members
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "team_members",
        sa.Column("team_id",   sa.String(50), nullable=False),
        sa.Column("user_id",   sa.String(40), nullable=False),
        sa.Column("role",      sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["team_id"], ["teams.team_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "user_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 8. places  (PostGIS GEOMETRY 사용)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "places",
        sa.Column("place_id",        sa.String(50),  nullable=False),
        sa.Column("external_id",     sa.String(100), nullable=True),
        sa.Column("external_source", sa.String(30),  nullable=True),
        sa.Column("name",            sa.String(255), nullable=False),
        sa.Column("place_type",      sa.String(20),  nullable=False),
        sa.Column("description",     sa.Text(),      nullable=True),
        sa.Column("address",         sa.String(255), nullable=True),
        sa.Column("geom",            Geometry("POINT", srid=4326), nullable=True),
        sa.Column("region_code",     sa.String(50),  nullable=True),
        sa.Column("contact_info",    sa.String(100), nullable=True),
        sa.Column("opening_hours",   postgresql.JSONB(), nullable=True),
        sa.Column("price_range",     sa.String(20),  nullable=True),
        sa.Column("created_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("place_id"),
        sa.UniqueConstraint("external_source", "external_id", name="uq_place_external"),
    )

    # ──────────────────────────────────────────────────────────
    # 9. weather_snapshots
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "weather_snapshots",
        sa.Column("weather_id",     sa.String(50), nullable=False),
        sa.Column("region_code",    sa.String(50), nullable=False),
        sa.Column("target_date",    sa.Date(),     nullable=False),
        sa.Column("condition_code", sa.Integer(),  nullable=False),
        sa.Column("temp_min",       sa.Numeric(4, 1), nullable=True),
        sa.Column("temp_max",       sa.Numeric(4, 1), nullable=True),
        sa.Column("rain_prob",      sa.Integer(),  nullable=True),
        sa.Column("wind_speed",     sa.Numeric(4, 1), nullable=True),
        sa.Column("fetched_at",     postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("weather_id"),
        sa.UniqueConstraint("region_code", "target_date", name="uq_weather_region_date"),
    )

    # ──────────────────────────────────────────────────────────
    # 10. trips
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "trips",
        sa.Column("trip_id",         sa.String(50),  nullable=False),
        sa.Column("team_id",         sa.String(50),  nullable=False),
        sa.Column("created_by",      sa.String(40),  nullable=False),
        sa.Column("title",           sa.String(255), nullable=False),
        sa.Column("destination",     sa.String(100), nullable=False),
        sa.Column("start_date",      sa.Date(),      nullable=False),
        sa.Column("end_date",        sa.Date(),      nullable=False),
        sa.Column("expected_budget", sa.Numeric(15, 2), nullable=True),
        sa.Column("cover_img_url",   sa.Text(),      nullable=True),
        sa.Column("status",          sa.String(20),  nullable=False, server_default="planning"),
        sa.Column("created_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["team_id"],    ["teams.team_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("trip_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 11. trip_days
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "trip_days",
        sa.Column("day_id",      sa.String(50), nullable=False),
        sa.Column("trip_id",     sa.String(50), nullable=False),
        sa.Column("day_number",  sa.Integer(),  nullable=False),
        sa.Column("target_date", sa.Date(),     nullable=False),
        sa.Column("weather_id",  sa.String(50), nullable=True),
        sa.Column("daily_memo",  sa.Text(),     nullable=True),
        sa.ForeignKeyConstraint(["trip_id"],    ["trips.trip_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["weather_id"], ["weather_snapshots.weather_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("day_id"),
        sa.UniqueConstraint("trip_id", "day_number",  name="uq_tripday_number"),
        sa.UniqueConstraint("trip_id", "target_date", name="uq_tripday_date"),
    )

    # ──────────────────────────────────────────────────────────
    # 12. sessions
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("session_id",      sa.String(50),  nullable=False),
        sa.Column("trip_id",         sa.String(50),  nullable=True),
        sa.Column("title",           sa.String(255), nullable=True),
        sa.Column("is_manual_title", sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("topic",           sa.Text(),      nullable=True),
        sa.Column("context_summary", sa.Text(),      nullable=True),
        sa.Column("is_active",       sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("session_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 13. session_participants
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "session_participants",
        sa.Column("session_id",   sa.String(50), nullable=False),
        sa.Column("user_id",      sa.String(40), nullable=False),
        sa.Column("role",         sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("last_read_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"],    ["users.user_id"],       ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "user_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 14. conversations
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("message_id",   sa.String(50), nullable=False),
        sa.Column("session_id",   sa.String(50), nullable=False),
        sa.Column("sender_id",    sa.String(40), nullable=True),
        sa.Column("sender_type",  sa.String(20), nullable=False),   # DEFAULT 없음 — 반드시 명시
        sa.Column("message_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("content",      sa.Text(),     nullable=False),
        sa.Column("created_at",   postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"],  ["users.user_id"],       ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("message_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 15. proposals
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "proposals",
        sa.Column("proposal_id",     sa.String(50), nullable=False),
        sa.Column("message_id",      sa.String(50), nullable=False),
        sa.Column("target_day_id",   sa.String(50), nullable=False),
        sa.Column("place_id",        sa.String(50), nullable=False),
        sa.Column("suggested_order", sa.Integer(),  nullable=True),
        sa.Column("suggested_time",  sa.Time(),     nullable=True),
        sa.Column("status",          sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resolved_by",     sa.String(40), nullable=True),
        sa.Column("resolved_at",     postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["message_id"],    ["conversations.message_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_day_id"], ["trip_days.day_id"],         ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"],      ["places.place_id"],          ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"],   ["users.user_id"],            ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("proposal_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 16. itinerary_items
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "itinerary_items",
        sa.Column("item_id",        sa.String(50), nullable=False),
        sa.Column("day_id",         sa.String(50), nullable=False),
        sa.Column("place_id",       sa.String(50), nullable=True),
        sa.Column("proposal_id",    sa.String(50), nullable=True),
        sa.Column("visit_order",    sa.Integer(),  nullable=False),
        sa.Column("start_time",     sa.Time(),     nullable=True),
        sa.Column("end_time",       sa.Time(),     nullable=True),
        sa.Column("transport_mode", sa.String(20), nullable=True),
        sa.Column("map_route_data", postgresql.JSONB(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("memo",           sa.Text(),     nullable=True),
        sa.Column("status",         sa.String(20), nullable=False, server_default="proposed"),
        sa.ForeignKeyConstraint(["day_id"],      ["trip_days.day_id"],       ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"],    ["places.place_id"],        ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"],  ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("item_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 17. session_markers
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "session_markers",
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("place_id",   sa.String(50), nullable=False),
        sa.Column("marker_id",  sa.String(50), nullable=False),
        sa.Column("created_by", sa.String(10), nullable=False, server_default="user"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"],   ["places.place_id"],     ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "place_id"),
        sa.UniqueConstraint("session_id", "marker_id", name="uq_marker_per_session"),
    )

    # ──────────────────────────────────────────────────────────
    # 18. session_files
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "session_files",
        sa.Column("file_id",     sa.String(50),  nullable=False),
        sa.Column("session_id",  sa.String(50),  nullable=False),
        sa.Column("message_id",  sa.String(50),  nullable=True),
        sa.Column("uploader_id", sa.String(40),  nullable=False),
        sa.Column("file_url",    sa.Text(),      nullable=False),
        sa.Column("file_name",   sa.String(255), nullable=False),
        sa.Column("file_type",   sa.String(50),  nullable=False),
        sa.Column("uploaded_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"],  ["sessions.session_id"],      ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"],  ["conversations.message_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.user_id"],            ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("file_id"),
    )

    # ──────────────────────────────────────────────────────────
    # 19. notifications
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.String(50), nullable=False),
        sa.Column("user_id",         sa.String(40), nullable=False),
        sa.Column("type",            sa.String(40), nullable=False),
        sa.Column("reference_type",  sa.String(20), nullable=False),
        sa.Column("reference_id",    sa.String(50), nullable=False),
        sa.Column("message",         sa.Text(),     nullable=False),
        sa.Column("is_read",         sa.Boolean(),  nullable=False, server_default="false"),
        sa.Column("created_at",      postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id"),
    )


def downgrade() -> None:
    # FK 역순으로 삭제
    tables = [
        "notifications",
        "session_files",
        "session_markers",
        "itinerary_items",
        "proposals",
        "conversations",
        "session_participants",
        "sessions",
        "trip_days",
        "trips",
        "team_members",
        "teams",
        "user_preferences",
        "user_profile",
        "user_security",
        "user_oauth",
        "users",
        "weather_snapshots",
        "places",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
