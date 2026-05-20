import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from alembic import context
from sqlalchemy import engine_from_config, pool

# =========================================================
# 경로 및 환경 변수 설정
# =========================================================

# 프로젝트 루트(/app)를 sys.path에 추가하여 module 임포트 보장
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# setting/.env 로드
load_dotenv(PROJECT_ROOT / "setting" / ".env")

# =========================================================
# SQLAlchemy 모델 임포트 (Alembic autogenerate 감지 대상)
# =========================================================

from module.node.memory.postgres_tables import Base  # noqa: E402

target_metadata = Base.metadata

# =========================================================
# DATABASE_URL 주입
# =========================================================

def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL 환경 변수가 설정되지 않았습니다. setting/.env를 확인하세요."
        )
    return url


# =========================================================
# Alembic 실행 모드
# =========================================================

def run_migrations_offline() -> None:
    """
    오프라인 모드: DB 연결 없이 SQL 스크립트 파일만 생성합니다.
    CI/CD 파이프라인에서 미리 SQL을 뽑아볼 때 유용합니다.
    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    온라인 모드: 실제 DB에 연결하여 마이그레이션을 적용합니다.
    """
    configuration = context.config.get_section(context.config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,       # 칼럼 타입 변경도 감지
            compare_server_default=True,  # 기본값 변경도 감지
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
