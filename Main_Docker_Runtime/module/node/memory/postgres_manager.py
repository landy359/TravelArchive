import asyncio
import datetime
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

try:
    from geoalchemy2.elements import WKBElement
    from geoalchemy2.shape import to_shape
    import shapely.wkt
    HAS_GEOALCHEMY = True
except ImportError:
    HAS_GEOALCHEMY = False
    print("[PostgresManager] GeoAlchemy2가 설치되지 않아 공간 데이터 변환 기능을 비활성화합니다.")


class PostgresManager:
    """
    PostgreSQL(PostGIS) 전용 동기 SQLAlchemy 매니저.
    싱글톤 패턴으로 db_url 당 하나의 인스턴스만 유지합니다.
    asyncio.to_thread를 통해 비동기 환경에서 안전하게 호출됩니다.

    지원 액션:
        create     : 단일 행 삽입
        read       : 필터 기반 행 조회 (limit/offset 지원)
        update     : 필터 기반 행 수정
        delete     : 필터 기반 행 삭제
        raw_sql    : 원시 SQL 직접 실행 (마이그레이션, 복잡 쿼리용)
    """

    _instances = {}
    _global_registry = {}  # 모든 인스턴스가 공유하는 모델 레지스트리

    def __new__(cls, db_url=None):
        if db_url is None:
            db_url = os.getenv("DATABASE_URL", "sqlite:///./default.db")

        if db_url not in cls._instances:
            instance = super(PostgresManager, cls).__new__(cls)
            instance._init_db(db_url)
            cls._instances[db_url] = instance

        return cls._instances[db_url]

    def _init_db(self, db_url: str):
        print(f"[PostgresManager] 엔진 가동 (URL: {db_url})")

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        self.engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    # =========================================================
    # 모델 등록 및 테이블 생성
    # =========================================================

    def register_model(self, model_name: str, model_class):
        PostgresManager._global_registry[model_name] = model_class
        print(f"[PostgresManager] 모델 등록 완료: {model_name}")

    def create_tables(self, base_metadata):
        base_metadata.create_all(bind=self.engine)
        print("[PostgresManager] 데이터베이스 테이블 물리적 생성 완료")

    # =========================================================
    # 비동기 진입점 (FastAPI/asyncio에서 호출)
    # =========================================================

    async def execute(self, payload: dict) -> dict:
        """
        동기 _sync_execute를 스레드풀에서 실행하여 이벤트 루프를 블로킹하지 않습니다.
        """
        return await asyncio.to_thread(self._sync_execute, payload)

    # =========================================================
    # 동기 CRUD 실행부
    # =========================================================

    def _sync_execute(self, payload: dict) -> dict:
        action = payload.get("action")
        model_name = payload.get("model")

        if not action:
            return {"status": "error", "reason": "Payload must contain 'action'"}

        # model이 필요한 액션은 registry에서 조회
        model_class = None
        if model_name:
            model_class = PostgresManager._global_registry.get(model_name)
            if not model_class:
                return {"status": "error", "reason": f"Model '{model_name}' is not registered"}

        session = self.SessionLocal()
        try:
            result = self._dispatch(session, action, model_class, payload)
            return result
        except Exception as e:
            session.rollback()
            print(f"[PostgresManager] 실행 오류 (action={action}): {e}")
            return {"status": "error", "reason": str(e)}
        finally:
            session.close()

    def _dispatch(self, session, action: str, model_class, payload: dict) -> dict:

        # ------------------------------------------
        # CREATE: 단일 행 삽입
        # payload: {action, model, data: {col: val}}
        # ------------------------------------------
        if action == "create":
            if not model_class:
                return {"status": "error", "reason": "Model required for 'create'"}

            data = payload.get("data", {})
            obj = model_class(**data)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return {"status": "success", "action": "create", "data": self._to_dict(obj)}

        # ------------------------------------------
        # READ: 필터 기반 행 조회
        # payload: {action, model, filters: {}, limit, offset}
        # ------------------------------------------
        elif action == "read":
            if not model_class:
                return {"status": "error", "reason": "Model required for 'read'"}

            filters = payload.get("filters", {})
            limit   = payload.get("limit")
            offset  = payload.get("offset", 0)

            query = session.query(model_class)
            for col, val in filters.items():
                query = query.filter(getattr(model_class, col) == val)
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            rows = query.all()
            return {
                "status": "success",
                "action": "read",
                "data": [self._to_dict(r) for r in rows]
            }

        # ------------------------------------------
        # UPDATE: 필터 기반 행 수정
        # payload: {action, model, filters: {}, data: {col: val}}
        # ------------------------------------------
        elif action == "update":
            if not model_class:
                return {"status": "error", "reason": "Model required for 'update'"}

            filters = payload.get("filters", {})
            data    = payload.get("data", {})

            query = session.query(model_class)
            for col, val in filters.items():
                query = query.filter(getattr(model_class, col) == val)

            updated = query.update(data, synchronize_session="fetch")
            session.commit()
            return {"status": "success", "action": "update", "updated_count": updated}

        # ------------------------------------------
        # DELETE: 필터 기반 행 삭제
        # payload: {action, model, filters: {}}
        # ------------------------------------------
        elif action == "delete":
            if not model_class:
                return {"status": "error", "reason": "Model required for 'delete'"}

            filters = payload.get("filters", {})

            query = session.query(model_class)
            for col, val in filters.items():
                query = query.filter(getattr(model_class, col) == val)

            deleted = query.delete(synchronize_session="fetch")
            session.commit()
            return {"status": "success", "action": "delete", "deleted_count": deleted}

        # ------------------------------------------
        # RAW_SQL: 원시 SQL 직접 실행
        # payload: {action, sql, params: {}}
        # ------------------------------------------
        elif action == "raw_sql":
            sql    = payload.get("sql")
            params = payload.get("params", {})

            if not sql:
                return {"status": "error", "reason": "'sql' field required for 'raw_sql'"}

            result = session.execute(text(sql), params)
            session.commit()

            try:
                rows = result.fetchall()
                return {
                    "status": "success",
                    "action": "raw_sql",
                    "data": [dict(r._mapping) for r in rows]
                }
            except Exception:
                # INSERT/UPDATE/DELETE 등 반환값이 없는 쿼리
                return {"status": "success", "action": "raw_sql", "data": []}

        else:
            return {"status": "error", "reason": f"Unsupported action: '{action}'"}

    # =========================================================
    # 공간 데이터 포함 직렬화 헬퍼
    # =========================================================

    def _to_dict(self, obj) -> dict:
        if not obj:
            return {}
        result = {}
        for c in obj.__table__.columns:
            value = getattr(obj, c.name)
            if isinstance(value, datetime.datetime):
                result[c.name] = value.isoformat()
            elif HAS_GEOALCHEMY and isinstance(value, WKBElement):
                shapely_geom = to_shape(value)
                result[c.name] = shapely.wkt.dumps(shapely_geom)
            else:
                result[c.name] = value
        return result
