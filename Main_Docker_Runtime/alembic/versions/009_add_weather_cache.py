"""add weather_cache table for dDB kernel

Revision ID: 009
Revises: 008
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_cache",
        sa.Column("id",            sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("location",      sa.String(100),   nullable=False),
        sa.Column("forecast_date", sa.String(8),     nullable=False),   # YYYYMMDD
        sa.Column("forecast_time", sa.String(2),     nullable=False),   # 09|12|15|18
        sa.Column("summary",       sa.String(100),   nullable=False, server_default=""),
        sa.Column("rain_prob",     sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("temperature",   sa.Float(),       nullable=False, server_default="0"),
        sa.Column("humidity",      sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("wind_speed",    sa.Float(),       nullable=False, server_default="0"),
        sa.Column("source_type",   sa.String(10),    nullable=False, server_default=""),  # short|mid
        sa.Column("fetched_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",    sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_weather_cache_lookup",
        "weather_cache",
        ["forecast_date", "location", "forecast_time"],
    )
    op.create_index(
        "ix_weather_cache_expires",
        "weather_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_weather_cache_expires", table_name="weather_cache")
    op.drop_index("ix_weather_cache_lookup", table_name="weather_cache")
    op.drop_table("weather_cache")
