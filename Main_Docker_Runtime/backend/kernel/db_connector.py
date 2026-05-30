"""
[역할] Kernel 전용 범용 DB 커넥터.
       Memory 계층(memory/adapters.py)과 완전히 독립.
       기본 4종(SELECT/INSERT/UPDATE/DELETE) + PostGIS 거리(select_nearby) + raw SQL(execute_raw).
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generator, Mapping

from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor


# ────────────────────────────────────────────────────
# Kernel DB 테이블 상수
# ────────────────────────────────────────────────────

SDB_TABLE = "places"         # 정적 장소 DB
ALIAS_TABLE = "alias"        # places 1:N 별칭 테이블 (alias_id, place_id, alias)
DDB_TABLE = "weather_cache"  # 동적 날씨 캐시


# ────────────────────────────────────────────────────
# 내부 유틸
# ────────────────────────────────────────────────────

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_id(name: str) -> sql.Identifier:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return sql.Identifier(name)


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: _serialize(v) for k, v in row.items()}


def _where_clause(where: dict[str, Any], prefix: str = "w") -> tuple[sql.Composable, dict[str, Any]]:
    clauses = [
        sql.SQL("{} = {}").format(_safe_id(k), sql.Placeholder(f"{prefix}_{k}"))
        for k in where
    ]
    params = {f"{prefix}_{k}": v for k, v in where.items()}
    return sql.SQL(" AND ").join(clauses), params


# ────────────────────────────────────────────────────
# DBConnector
# ────────────────────────────────────────────────────

class DBConnector:
    """
    Kernel 전용 PostgreSQL 커넥터. SELECT / INSERT / UPDATE / DELETE.

    사용 예::

        conn = DBConnector()

        rows = await conn.select(
            SDB_TABLE,
            columns=["place_id", "name", "lat", "lon"],
            where={"region": "서울"},
        )

        row  = await conn.insert(SDB_TABLE, {"place_id": "p001", "name": "광화문"})
        n    = await conn.update(SDB_TABLE, where={"place_id": "p001"}, data={"alias": "광화문 광장"})
        n    = await conn.delete(SDB_TABLE, where={"place_id": "p001"})
    """

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or os.environ["DATABASE_URL"]
        self._pool = pool.ThreadedConnectionPool(1, 6, dsn=url)

    def close(self) -> None:
        self._pool.closeall()

    # ────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────

    async def select(
        self,
        table: str,
        *,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """SELECT columns FROM table WHERE conditions."""
        return await asyncio.to_thread(
            self._select_sync, table, columns or [], where or {}, limit
        )

    async def select_nearby(
        self,
        table: str,
        *,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        near: tuple[float, float],
        within_m: float,
        limit: int,
        geom_column: str = "geom",
    ) -> list[dict[str, Any]]:
        """PostGIS 거리 조회.

        ``WHERE <equality> AND ST_DWithin(geom, point, within_m)``
        ``ORDER BY ST_Distance(geom, point) ASC LIMIT limit``

        :param near: (lon, lat) — PostGIS 표준 좌표 순서.
        :param within_m: 검색 반경 (미터, geography 거리).
        """
        return await asyncio.to_thread(
            self._select_nearby_sync,
            table, columns or [], where or {}, near, within_m, limit, geom_column,
        )

    async def execute_raw(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Raw SQL escape hatch — JOIN/CTE/집계 등 4종 메서드로 표현 불가능한 쿼리용.

        호출자는 식별자(테이블/컬럼명)를 쿼리 문자열에 직접 박지 말고
        파라미터로 받는 값만 ``%(name)s`` placeholder 로 넘긴다.
        DDL(ALTER/CREATE)은 의도된 용도가 아니다.
        """
        return await asyncio.to_thread(self._execute_raw_sync, query, params or {})

    async def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """INSERT … RETURNING * → 삽입된 row 반환."""
        return await asyncio.to_thread(self._insert_sync, table, data)

    async def update(
        self, table: str, *, where: dict[str, Any], data: dict[str, Any]
    ) -> int:
        """UPDATE … SET … WHERE … → 변경된 row 수 반환."""
        return await asyncio.to_thread(self._update_sync, table, where, data)

    async def delete(self, table: str, *, where: dict[str, Any]) -> int:
        """DELETE FROM table WHERE … → 삭제된 row 수 반환."""
        return await asyncio.to_thread(self._delete_sync, table, where)

    # ────────────────────────────────────────────────
    # Sync internals
    # ────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator:
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _select_sync(
        self,
        table: str,
        columns: list[str],
        where: dict[str, Any],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                col_clause = (
                    sql.SQL(", ").join(_safe_id(c) for c in columns)
                    if columns else sql.SQL("*")
                )
                parts: list[sql.Composable] = [
                    sql.SQL("SELECT {} FROM {}").format(col_clause, _safe_id(table))
                ]
                params: dict[str, Any] = {}
                if where:
                    clause, params = _where_clause(where)
                    parts.append(sql.SQL(" WHERE ") + clause)
                if limit is not None:
                    parts.append(sql.SQL(" LIMIT {}").format(sql.Literal(int(limit))))
                cur.execute(sql.SQL("").join(parts), params)
                return [_serialize_row(r) for r in cur.fetchall()]

    def _select_nearby_sync(
        self,
        table: str,
        columns: list[str],
        where: dict[str, Any],
        near: tuple[float, float],
        within_m: float,
        limit: int,
        geom_column: str,
    ) -> list[dict[str, Any]]:
        lon, lat = near
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                col_clause = (
                    sql.SQL(", ").join(_safe_id(c) for c in columns)
                    if columns else sql.SQL("*")
                )
                geom_id = _safe_id(geom_column)
                point_expr = sql.SQL(
                    "ST_SetSRID(ST_MakePoint({}, {}), 4326)::geography"
                ).format(sql.Placeholder("_lon"), sql.Placeholder("_lat"))

                params: dict[str, Any] = {
                    "_lon": float(lon),
                    "_lat": float(lat),
                    "_radius": float(within_m),
                    "_limit": int(limit),
                }

                parts: list[sql.Composable] = [
                    sql.SQL("SELECT {} FROM {} WHERE ").format(col_clause, _safe_id(table))
                ]
                if where:
                    eq_clause, eq_params = _where_clause(where)
                    parts.append(eq_clause)
                    parts.append(sql.SQL(" AND "))
                    params.update(eq_params)
                parts.append(
                    sql.SQL("ST_DWithin({}::geography, {}, {})").format(
                        geom_id, point_expr, sql.Placeholder("_radius")
                    )
                )
                parts.append(
                    sql.SQL(" ORDER BY ST_Distance({}::geography, {}) ASC LIMIT {}").format(
                        geom_id, point_expr, sql.Placeholder("_limit")
                    )
                )

                cur.execute(sql.SQL("").join(parts), params)
                return [_serialize_row(r) for r in cur.fetchall()]

    def _insert_sync(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            raise ValueError("insert: data must not be empty")
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = sql.SQL(
                    "INSERT INTO {} ({}) VALUES ({}) RETURNING *"
                ).format(
                    _safe_id(table),
                    sql.SQL(", ").join(_safe_id(k) for k in data),
                    sql.SQL(", ").join(sql.Placeholder(k) for k in data),
                )
                cur.execute(query, data)
                return _serialize_row(cur.fetchone() or {})

    def _update_sync(
        self, table: str, where: dict[str, Any], data: dict[str, Any]
    ) -> int:
        if not data:
            raise ValueError("update: data must not be empty")
        if not where:
            raise ValueError("update: where must not be empty")
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                assignments = [
                    sql.SQL("{} = {}").format(_safe_id(k), sql.Placeholder(f"d_{k}"))
                    for k in data
                ]
                where_sql, where_params = _where_clause(where)
                query = sql.SQL("UPDATE {} SET {} WHERE {}").format(
                    _safe_id(table),
                    sql.SQL(", ").join(assignments),
                    where_sql,
                )
                cur.execute(query, {f"d_{k}": v for k, v in data.items()} | where_params)
                return cur.rowcount

    def _delete_sync(self, table: str, where: dict[str, Any]) -> int:
        if not where:
            raise ValueError("delete: where must not be empty")
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                where_sql, params = _where_clause(where)
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE {}").format(_safe_id(table), where_sql),
                    params,
                )
                return cur.rowcount

    def _execute_raw_sync(
        self, query: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if cur.description is None:
                    return []
                return [_serialize_row(r) for r in cur.fetchall()]
