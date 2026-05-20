from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, TypeAlias

from .constants import MAX_BUFFER_SESSIONS

import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
import redis.asyncio as redis_async


Payload: TypeAlias = dict[str, Any]
Result: TypeAlias = dict[str, Any]
Row: TypeAlias = dict[str, Any]


_MODEL_TABLES: dict[str, str] = {
    "User": "users",
    "UserProfile": "user_profile",
    "UserSecurity": "user_security",
    "UserOAuth": "user_oauth",
    "UserPreferences": "user_preferences",
    "Team": "teams",
    "TeamMember": "team_members",
    "Trip": "trips",
    "Session": "sessions",
    "SessionParticipant": "session_participants",
    "Conversation": "conversations",
    "Notification": "notifications",
}

_NAMED_PARAM_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PgAdapter:
    def __init__(self, database_url: str) -> None:
        self._pool = pool.ThreadedConnectionPool(2, 10, dsn=database_url)

    async def execute(self, payload: Payload) -> Result:
        return await asyncio.to_thread(self._execute_sync, payload)

    def close(self) -> None:
        self._pool.closeall()

    async def query(self, raw_sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        result = await self.execute({"action": "raw_sql", "sql": raw_sql, "params": params or {}})
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "pg query failed"))
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    async def create(self, model: str, data: dict[str, Any]) -> Row:
        result = await self.execute({"action": "create", "model": model, "data": data})
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "pg create failed"))
        row = result.get("data", {})
        return row if isinstance(row, dict) else {}

    async def read(self, model: str, filters: dict[str, Any] | None = None) -> list[Row]:
        result = await self.execute({"action": "read", "model": model, "filters": filters or {}})
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "pg read failed"))
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    async def update(self, model: str, filters: dict[str, Any], data: dict[str, Any]) -> int:
        result = await self.execute({"action": "update", "model": model, "filters": filters, "data": data})
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "pg update failed"))
        return int(result.get("updated_count", 0))

    async def delete_row(self, model: str, filters: dict[str, Any]) -> int:
        result = await self.execute({"action": "delete", "model": model, "filters": filters})
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "pg delete failed"))
        return int(result.get("deleted_count", 0))

    def _execute_sync(self, payload: Payload) -> Result:
        action = payload.get("action")
        if not isinstance(action, str) or not action:
            return _error("Payload must contain 'action'")

        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                result = self._dispatch(cursor, action, payload)
            conn.commit()
            return result
        except Exception as exc:
            conn.rollback()
            return _error(str(exc))
        finally:
            self._pool.putconn(conn)

    def _dispatch(self, cursor: RealDictCursor, action: str, payload: Payload) -> Result:
        handlers: dict[str, Callable[[RealDictCursor, Payload], Result]] = {
            "create": self._create,
            "read": self._read,
            "update": self._update,
            "delete": self._delete,
            "raw_sql": self._raw_sql,
        }
        handler = handlers.get(action)
        if handler is None:
            return _error(f"Unsupported action: '{action}'")
        return handler(cursor, payload)

    def _create(self, cursor: RealDictCursor, payload: Payload) -> Result:
        table = _table_for_payload(payload)
        data = _mapping_payload(payload, "data")
        if not data:
            return _error("'data' required for 'create'")

        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(key) for key in data),
            sql.SQL(", ").join(sql.Placeholder(key) for key in data),
        )
        cursor.execute(query, data)
        row = cursor.fetchone()
        return {"status": "success", "action": "create", "data": _serialize_row(row or {})}

    def _read(self, cursor: RealDictCursor, payload: Payload) -> Result:
        table = _table_for_payload(payload)
        filters = _mapping_payload(payload, "filters", allow_empty=True)
        query, params = _select_query(table, filters, payload.get("limit"), payload.get("offset"))
        cursor.execute(query, params)
        rows = [_serialize_row(row) for row in cursor.fetchall()]
        return {"status": "success", "action": "read", "data": rows}

    def _update(self, cursor: RealDictCursor, payload: Payload) -> Result:
        table = _table_for_payload(payload)
        filters = _mapping_payload(payload, "filters")
        data = _mapping_payload(payload, "data")
        if not data:
            return _error("'data' required for 'update'")

        query, params = _update_query(table, filters, data)
        cursor.execute(query, params)
        return {"status": "success", "action": "update", "updated_count": cursor.rowcount}

    def _delete(self, cursor: RealDictCursor, payload: Payload) -> Result:
        table = _table_for_payload(payload)
        filters = _mapping_payload(payload, "filters")
        query, params = _delete_query(table, filters)
        cursor.execute(query, params)
        return {"status": "success", "action": "delete", "deleted_count": cursor.rowcount}

    def _raw_sql(self, cursor: RealDictCursor, payload: Payload) -> Result:
        raw = payload.get("sql")
        if not isinstance(raw, str) or not raw.strip():
            return _error("'sql' field required for 'raw_sql'")

        params = _mapping_payload(payload, "params", allow_empty=True)
        cursor.execute(_convert_named_params(raw), params)
        rows = cursor.fetchall() if cursor.description else []
        return {"status": "success", "action": "raw_sql", "data": [_serialize_row(row) for row in rows]}


class RedisAdapter:
    def __init__(self, redis_url: str) -> None:
        self._redis = redis_async.from_url(redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._redis.aclose()

    async def get_json(self, key: str) -> Any:
        result = await self.execute({"action": "get", "key": key})
        value = result.get("value")
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload: Payload = {
            "action": "set",
            "key": key,
            "value": json.dumps(value, ensure_ascii=False, default=str),
        }
        if ttl is not None:
            payload["ttl"] = ttl
        result = await self.execute(payload)
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "redis set_json failed"))

    async def get_str(self, key: str) -> str | None:
        result = await self.execute({"action": "get", "key": key})
        value = result.get("value")
        return value if isinstance(value, str) else None

    async def set_str(self, key: str, value: str, ttl: int | None = None) -> None:
        payload: Payload = {"action": "set", "key": key, "value": value}
        if ttl is not None:
            payload["ttl"] = ttl
        result = await self.execute(payload)
        if result.get("status") != "success":
            raise RuntimeError(result.get("reason", "redis set_str failed"))

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def exists_many(self, keys: list[str]) -> set[str]:
        """파이프라인으로 여러 키의 존재 여부를 한 번에 조회한다."""
        if not keys:
            return set()
        pipe = self._redis.pipeline()
        for key in keys:
            pipe.exists(key)
        results = await pipe.execute()
        return {k for k, found in zip(keys, results) if found}

    async def scan(self, pattern: str) -> list[str]:
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self._redis.scan(cursor, match=pattern, count=100)
            keys.extend(str(k) for k in batch)
            if cursor == 0:
                return keys

    async def execute(self, payload: Payload) -> Result:
        action = payload.get("action")
        key = payload.get("key")
        if not isinstance(action, str) or not action:
            return _error("Payload must contain 'action'")
        if not isinstance(key, str) or not key:
            return _error("Payload must contain 'key'")

        try:
            return await self._dispatch(action, key, payload)
        except Exception as exc:
            return _error(str(exc))

    async def _dispatch(self, action: str, key: str, payload: Payload) -> Result:
        handlers: dict[str, Callable[[str, Payload], Any]] = {
            "get": self._get,
            "set": self._set,
            "delete": self._delete,
            "hget": self._hget,
            "hset": self._hset,
            "hgetall": self._hgetall,
            "sadd": self._sadd,
            "srem": self._srem,
            "smembers": self._smembers,
            "expire": self._expire,
            "exists": self._exists,
        }
        handler = handlers.get(action)
        if handler is None:
            return _error(f"Unsupported action: '{action}'")
        return await handler(key, payload)

    async def _get(self, key: str, payload: Payload) -> Result:
        return {"status": "success", "value": await self._redis.get(key)}

    async def _set(self, key: str, payload: Payload) -> Result:
        value = payload.get("value")
        if value is None:
            return _error("'value' required for 'set'")
        ttl = payload.get("ttl")
        await self._redis.set(key, _redis_value(value), ex=int(ttl) if ttl else None)
        return {"status": "success"}

    async def _delete(self, key: str, payload: Payload) -> Result:
        await self._redis.delete(key)
        return {"status": "success"}

    async def _hget(self, key: str, payload: Payload) -> Result:
        field = payload.get("field")
        if not isinstance(field, str) or not field:
            return _error("'field' required for 'hget'")
        return {"status": "success", "value": await self._redis.hget(key, field)}

    async def _hset(self, key: str, payload: Payload) -> Result:
        mapping = payload.get("mapping")
        field = payload.get("field")
        value = payload.get("value")
        if isinstance(mapping, Mapping):
            await self._redis.hset(key, mapping={str(k): _redis_value(v) for k, v in mapping.items()})
        elif isinstance(field, str) and value is not None:
            await self._redis.hset(key, field, _redis_value(value))
        else:
            return _error("'mapping' or ('field' + 'value') required for 'hset'")
        if payload.get("ttl"):
            await self._redis.expire(key, int(payload["ttl"]))
        return {"status": "success"}

    async def _hgetall(self, key: str, payload: Payload) -> Result:
        return {"status": "success", "data": await self._redis.hgetall(key)}

    async def _sadd(self, key: str, payload: Payload) -> Result:
        members = _members(payload)
        if not members:
            return _error("'members' required for 'sadd'")
        await self._redis.sadd(key, *members)
        return {"status": "success"}

    async def _srem(self, key: str, payload: Payload) -> Result:
        members = _members(payload)
        if not members:
            return _error("'members' required for 'srem'")
        await self._redis.srem(key, *members)
        return {"status": "success"}

    async def _smembers(self, key: str, payload: Payload) -> Result:
        return {"status": "success", "data": await self._redis.smembers(key)}

    async def _expire(self, key: str, payload: Payload) -> Result:
        ttl = payload.get("ttl")
        if ttl is None:
            return _error("'ttl' required for 'expire'")
        await self._redis.expire(key, int(ttl))
        return {"status": "success"}

    async def _exists(self, key: str, payload: Payload) -> Result:
        return {"status": "success", "exists": bool(await self._redis.exists(key))}


class MapNode:
    def __init__(self) -> None:
        self._redis: RedisAdapter | None = None
        self._buffer: OrderedDict[str, dict[str, list[Any] | None]] = OrderedDict()

    def bind_redis(self, redis_adapter: RedisAdapter) -> None:
        self._redis = redis_adapter

    async def add_marker(self, session_id: str, marker_id: str, lat: float, lng: float, title: str) -> None:
        markers = [item for item in await self.get_markers(session_id) if item.get("marker_id") != marker_id]
        markers.append({"marker_id": marker_id, "lat": lat, "lng": lng, "title": title})
        await self.set_markers(session_id, markers)

    async def delete_marker(self, session_id: str, marker_id: str) -> None:
        markers = [item for item in await self.get_markers(session_id) if item.get("marker_id") != marker_id]
        await self.set_markers(session_id, markers)

    async def set_markers(self, session_id: str, markers: list[dict[str, Any]]) -> None:
        normalized = [_normalize_marker(marker) for marker in markers]
        self._session_buffer(session_id)["markers"] = normalized
        await self._set_json(f"session:{session_id}:markers", normalized)

    async def get_markers(self, session_id: str) -> list[dict[str, Any]]:
        cached = self._session_buffer(session_id)["markers"]
        if cached is None:
            cached = await self._get_json(f"session:{session_id}:markers")
            self._session_buffer(session_id)["markers"] = cached
        return list(cached)

    async def set_routes(self, session_id: str, marker_ids: list[str]) -> None:
        routes = [str(marker_id) for marker_id in marker_ids]
        self._session_buffer(session_id)["routes"] = routes
        await self._set_json(f"session:{session_id}:routes", routes)

    async def get_routes(self, session_id: str) -> list[str]:
        cached = self._session_buffer(session_id)["routes"]
        if cached is None:
            cached = await self._get_json(f"session:{session_id}:routes")
            self._session_buffer(session_id)["routes"] = cached
        return [str(item) for item in cached]

    def _session_buffer(self, session_id: str) -> dict[str, list[Any] | None]:
        if session_id in self._buffer:
            self._buffer.move_to_end(session_id)
        else:
            self._buffer[session_id] = {"markers": None, "routes": None}
            if len(self._buffer) > MAX_BUFFER_SESSIONS:
                self._buffer.popitem(last=False)
        return self._buffer[session_id]

    async def _get_json(self, key: str) -> list[Any]:
        return await _bound_redis(self._redis).get_json(key) or []

    async def _set_json(self, key: str, value: list[Any]) -> None:
        await _bound_redis(self._redis).set_json(key, value)


class TripRangeNode:
    def __init__(self) -> None:
        self._redis: RedisAdapter | None = None
        self._buffer: OrderedDict[str, list[Any]] = OrderedDict()

    def bind_redis(self, redis_adapter: RedisAdapter) -> None:
        self._redis = redis_adapter

    async def set(self, session_id: str, ranges: list[Any]) -> None:
        self._buffer[session_id] = ranges
        self._buffer.move_to_end(session_id)
        if len(self._buffer) > MAX_BUFFER_SESSIONS:
            self._buffer.popitem(last=False)
        await _bound_redis(self._redis).set_json(f"session:{session_id}:ranges", ranges)

    async def get(self, session_id: str) -> list[Any]:
        if session_id not in self._buffer:
            self._buffer[session_id] = await _bound_redis(self._redis).get_json(f"session:{session_id}:ranges") or []
            if len(self._buffer) > MAX_BUFFER_SESSIONS:
                self._buffer.popitem(last=False)
        else:
            self._buffer.move_to_end(session_id)
        return list(self._buffer[session_id])


def _table_for_payload(payload: Payload) -> str:
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("Model required")
    table = _MODEL_TABLES.get(model)
    if table is None:
        raise ValueError(f"Model '{model}' is not registered")
    return table


def _mapping_payload(payload: Payload, key: str, allow_empty: bool = False) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"'{key}' must be a mapping")
    data = dict(value)
    if not allow_empty and not data:
        raise ValueError(f"'{key}' required")
    for column in data:
        if not _IDENTIFIER_PATTERN.match(str(column)):
            raise ValueError(f"Invalid column name: {column}")
    return data


def _select_query(
    table: str,
    filters: Mapping[str, Any],
    limit: Any,
    offset: Any,
) -> tuple[sql.Composable, dict[str, Any]]:
    params = _prefixed_params("filter", filters)
    parts = [sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))]
    if filters:
        parts.append(sql.SQL(" WHERE ") + _where_clause("filter", filters))
    if offset:
        parts.append(sql.SQL(" OFFSET {}").format(sql.Literal(int(offset))))
    if limit:
        parts.append(sql.SQL(" LIMIT {}").format(sql.Literal(int(limit))))
    return sql.SQL("").join(parts), params


def _update_query(
    table: str,
    filters: Mapping[str, Any],
    data: Mapping[str, Any],
) -> tuple[sql.Composable, dict[str, Any]]:
    assignments = [
        sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder(f"data_{key}"))
        for key in data
    ]
    query = sql.SQL("UPDATE {} SET {} WHERE {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(assignments),
        _where_clause("filter", filters),
    )
    return query, _prefixed_params("data", data) | _prefixed_params("filter", filters)


def _delete_query(table: str, filters: Mapping[str, Any]) -> tuple[sql.Composable, dict[str, Any]]:
    query = sql.SQL("DELETE FROM {} WHERE {}").format(sql.Identifier(table), _where_clause("filter", filters))
    return query, _prefixed_params("filter", filters)


def _where_clause(prefix: str, filters: Mapping[str, Any]) -> sql.Composable:
    clauses = [
        sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder(f"{prefix}_{key}"))
        for key in filters
    ]
    return sql.SQL(" AND ").join(clauses)


def _prefixed_params(prefix: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in values.items()}


def _convert_named_params(raw_sql: str) -> str:
    return _NAMED_PARAM_PATTERN.sub(r"%(\1)s", raw_sql)


def _serialize_row(row: Mapping[str, Any]) -> Row:
    return {key: _serialize_value(value) for key, value in row.items()}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _redis_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _members(payload: Payload) -> list[str]:
    members = payload.get("members")
    if members is None and payload.get("member") is not None:
        members = [payload["member"]]
    if isinstance(members, (str, bytes)) or not isinstance(members, Iterable):
        return []
    return [str(member) for member in members]


def _normalize_marker(marker: Mapping[str, Any]) -> dict[str, Any]:
    marker_id = marker.get("marker_id") or marker.get("id")
    return {
        "marker_id": str(marker_id),
        "lat": marker.get("lat", 0),
        "lng": marker.get("lng", 0),
        "title": marker.get("title", ""),
    }


def _bound_redis(redis_adapter: RedisAdapter | None) -> RedisAdapter:
    if redis_adapter is None:
        raise RuntimeError("Redis adapter is not bound")
    return redis_adapter


def _error(reason: str) -> Result:
    return {"status": "error", "reason": reason}