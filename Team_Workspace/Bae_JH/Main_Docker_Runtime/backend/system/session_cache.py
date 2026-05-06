"""
session_cache.py
Redis를 통한 세션 상태 캐싱 레이어.

Redis Key 구조:
  user:{user_id}:active_sessions    → Set  : 현재 사용자가 열어둔 세션 ID 목록
  user:{user_id}:current_session    → String: 현재 화면에 띄운 세션 ID
  session:{session_id}:meta         → Hash : 세션 메타데이터 (title, topic, context 등)
  session:{session_id}:markers      → String(JSON): 지도 마커 목록
  session:{session_id}:ranges       → String(JSON): 여행 기간 목록
  session:{session_id}:memo:{date}  → String: 날짜별 메모
  session:{session_id}:plan:{date}  → String(JSON): 날짜별 플래너 항목
"""
import json
from typing import Optional

SESSION_TTL          = 3600 * 8    # 활성 세션 Redis 유지 시간 (8시간)
USER_SESSION_SET_TTL = 3600 * 24   # 사용자 활성 세션 Set TTL (24시간)
DATA_TTL             = 3600 * 24   # 마커/메모/플랜 TTL (24시간)


class SessionCache:

    # ── 활성 세션 Set 관리 ────────────────────────────────────

    @staticmethod
    async def mark_active(user_id: str, session_id: str, redis):
        await redis.execute({
            "action": "sadd",
            "key":    f"user:{user_id}:active_sessions",
            "member": session_id,
        })
        await redis.execute({
            "action": "expire",
            "key":    f"user:{user_id}:active_sessions",
            "ttl":    USER_SESSION_SET_TTL,
        })

    @staticmethod
    async def unmark_active(user_id: str, session_id: str, redis):
        await redis.execute({
            "action": "srem",
            "key":    f"user:{user_id}:active_sessions",
            "member": session_id,
        })

    @staticmethod
    async def get_active_session_ids(user_id: str, redis) -> set:
        result = await redis.execute({
            "action": "smembers",
            "key":    f"user:{user_id}:active_sessions",
        })
        return set(result.get("data", []))

    # ── 현재 세션 추적 ────────────────────────────────────────

    @staticmethod
    async def set_current_session(user_id: str, session_id: str, redis):
        await redis.execute({
            "action": "set",
            "key":    f"user:{user_id}:current_session",
            "value":  session_id,
            "ttl":    SESSION_TTL,
        })

    @staticmethod
    async def get_current_session(user_id: str, redis) -> Optional[str]:
        result = await redis.execute({
            "action": "get",
            "key":    f"user:{user_id}:current_session",
        })
        return result.get("value")

    # ── 세션 메타 캐시 ───────────────────────────────────────

    @staticmethod
    async def cache_session_meta(session_id: str, meta: dict, redis):
        await redis.execute({
            "action":  "hset",
            "key":     f"session:{session_id}:meta",
            "mapping": {k: str(v) for k, v in meta.items()},
            "ttl":     SESSION_TTL,
        })

    @staticmethod
    async def get_session_meta(session_id: str, redis) -> Optional[dict]:
        result = await redis.execute({
            "action": "hgetall",
            "key":    f"session:{session_id}:meta",
        })
        d = result.get("data", {})
        return d if d else None

    @staticmethod
    async def delete_session_cache(session_id: str, redis):
        await redis.execute({"action": "delete", "key": f"session:{session_id}:meta"})

    # ── 마커 (Redis JSON 저장) ────────────────────────────────

    @staticmethod
    async def save_markers(session_id: str, markers: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:markers",
            "value":  json.dumps(markers, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_markers(session_id: str, redis) -> list:
        result = await redis.execute({
            "action": "get",
            "key":    f"session:{session_id}:markers",
        })
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    # ── 폴리라인 경로 (정점 순서) ─────────────────────────────

    @staticmethod
    async def save_routes(session_id: str, marker_ids: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:routes",
            "value":  json.dumps(marker_ids, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_routes(session_id: str, redis) -> list:
        result = await redis.execute({
            "action": "get",
            "key":    f"session:{session_id}:routes",
        })
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    # ── 여행 기간 ─────────────────────────────────────────────

    @staticmethod
    async def save_ranges(session_id: str, ranges: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:ranges",
            "value":  json.dumps(ranges, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_ranges(session_id: str, redis) -> list:
        result = await redis.execute({
            "action": "get",
            "key":    f"session:{session_id}:ranges",
        })
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    # ── 메모 ──────────────────────────────────────────────────

    @staticmethod
    async def save_memo(session_id: str, date_key: str, memo: str, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:memo:{date_key}",
            "value":  memo,
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_memo(session_id: str, date_key: str, redis) -> str:
        result = await redis.execute({
            "action": "get",
            "key":    f"session:{session_id}:memo:{date_key}",
        })
        return result.get("value") or ""

    # ── 플래너 ────────────────────────────────────────────────

    @staticmethod
    async def save_plan(session_id: str, date_key: str, plan: list, redis):
        await redis.execute({
            "action": "set",
            "key":    f"session:{session_id}:plan:{date_key}",
            "value":  json.dumps(plan, ensure_ascii=False),
            "ttl":    DATA_TTL,
        })

    @staticmethod
    async def get_plan(session_id: str, date_key: str, redis) -> list:
        result = await redis.execute({
            "action": "get",
            "key":    f"session:{session_id}:plan:{date_key}",
        })
        val = result.get("value")
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return []

    # ── 캘린더 인디케이터 ────────────────────────────────────

    @staticmethod
    async def get_indicators(session_id: str, year: int, month: int, redis) -> list:
        """해당 월에 메모 또는 플랜이 있는 날짜 목록."""
        prefix = f"{year}-{month:02d}-"
        # Redis scan으로 해당 세션의 memo/plan 키를 조회 (간단 구현)
        # 실제 스캔 대신 known 키 패턴으로 날짜 유추 (31일 기준)
        dates = set()
        import asyncio
        tasks = []
        for day in range(1, 32):
            date_key = f"{year}-{month:02d}-{day:02d}"
            tasks.append((date_key, session_id))

        for date_key, sid in tasks:
            memo_r = await redis.execute({"action": "exists", "key": f"session:{sid}:memo:{date_key}"})
            plan_r = await redis.execute({"action": "exists", "key": f"session:{sid}:plan:{date_key}"})
            if memo_r.get("exists") or plan_r.get("exists"):
                dates.add(date_key)

        return list(dates)
