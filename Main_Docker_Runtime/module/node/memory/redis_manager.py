import json
import os

import redis.asyncio as redis


class RedisManager:
    """
    Redis 전용 순수 비동기 매니저.
    싱글톤 패턴으로 redis_url 당 하나의 인스턴스만 유지합니다.

    지원 액션:
        [String]
            set        : 값 저장 (ttl 옵션)
            get        : 값 조회
            delete     : 키 삭제
            exists     : 키 존재 여부

        [Hash]  ← session:meta, user:GST 등 구조화 데이터
            hset       : 해시 필드 저장 (단일 또는 다중)
            hget       : 해시 단일 필드 조회
            hgetall    : 해시 전체 조회
            hdel       : 해시 단일 필드 삭제

        [List]  ← queue:tasks (작업 큐)
            lpush      : 리스트 왼쪽 삽입 (큐 enqueue)
            rpush      : 리스트 오른쪽 삽입
            lpop       : 리스트 왼쪽 꺼내기
            lrange     : 리스트 범위 조회

        [Set]   ← user:{user_id}:sessions
            sadd       : Set에 멤버 추가
            smembers   : Set 전체 멤버 조회
            srem       : Set에서 멤버 삭제

        [TTL]
            expire     : 특정 키에 TTL(초) 설정
            ttl        : 특정 키의 남은 TTL(초) 조회
    """

    _instances = {}

    def __new__(cls, redis_url=None):
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        if redis_url not in cls._instances:
            instance = super(RedisManager, cls).__new__(cls)
            instance._init_redis(redis_url)
            cls._instances[redis_url] = instance

        return cls._instances[redis_url]

    def _init_redis(self, redis_url: str):
        print(f"[RedisManager] 순수 비동기 엔진 가동 (URL: {redis_url})")
        self.redis = redis.from_url(redis_url, decode_responses=True)

    # =========================================================
    # 비동기 진입점
    # =========================================================

    async def execute(self, payload: dict) -> dict:
        action = payload.get("action")
        key    = payload.get("key")

        if not action:
            return {"status": "error", "reason": "Payload must contain 'action'"}

        # TTL 전용 액션은 key 필수
        # smembers, lrange 등 key 없이 의미없는 액션도 key 체크
        if action not in () and not key:
            return {"status": "error", "reason": "Payload must contain 'key'"}

        try:
            return await self._dispatch(action, key, payload)
        except redis.RedisError as e:
            print(f"[RedisManager] Redis Error: {e}")
            return {"status": "error", "reason": f"Redis error: {e}"}
        except Exception as e:
            print(f"[RedisManager] Unexpected Error: {e}")
            return {"status": "error", "reason": f"Unexpected error: {e}"}

    # =========================================================
    # 액션 디스패처
    # =========================================================

    async def _dispatch(self, action: str, key: str, payload: dict) -> dict:

        # ------------------------------------------
        # String: set / get / delete / exists
        # ------------------------------------------
        if action == "set":
            value = payload.get("value")
            ttl   = payload.get("ttl")  # 초 단위

            if value is None:
                return {"status": "error", "reason": "'value' required for 'set'"}

            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(value)

            if ttl:
                await self.redis.setex(key, int(ttl), value)
            else:
                await self.redis.set(key, value)

            return {"status": "success", "action": "set", "key": key}

        elif action == "get":
            value = await self.redis.get(key)
            return {"status": "success", "action": "get", "key": key, "value": value}

        elif action == "delete":
            count = await self.redis.delete(key)
            return {"status": "success", "action": "delete", "key": key, "deleted_count": count}

        elif action == "exists":
            result = await self.redis.exists(key)
            return {"status": "success", "action": "exists", "key": key, "exists": bool(result)}

        # ------------------------------------------
        # Hash: hset / hget / hgetall / hdel
        # payload 예시:
        #   hset    → {action, key, field, value}
        #             또는 다중: {action, key, mapping: {f1:v1, f2:v2}}
        #   hget    → {action, key, field}
        #   hgetall → {action, key}
        #   hdel    → {action, key, field}
        # ------------------------------------------
        elif action == "hset":
            mapping = payload.get("mapping")
            field   = payload.get("field")
            value   = payload.get("value")

            if mapping:
                # 다중 필드 저장: 값이 dict/list면 JSON 직렬화
                safe_mapping = {
                    k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                    for k, v in mapping.items()
                }
                await self.redis.hset(key, mapping=safe_mapping)
            elif field is not None and value is not None:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                await self.redis.hset(key, field, str(value))
            else:
                return {"status": "error", "reason": "'mapping' or ('field' + 'value') required for 'hset'"}

            ttl = payload.get("ttl")
            if ttl:
                await self.redis.expire(key, int(ttl))

            return {"status": "success", "action": "hset", "key": key}

        elif action == "hget":
            field = payload.get("field")
            if not field:
                return {"status": "error", "reason": "'field' required for 'hget'"}
            value = await self.redis.hget(key, field)
            return {"status": "success", "action": "hget", "key": key, "field": field, "value": value}

        elif action == "hgetall":
            data = await self.redis.hgetall(key)
            return {"status": "success", "action": "hgetall", "key": key, "data": data}

        elif action == "hdel":
            field = payload.get("field")
            if not field:
                return {"status": "error", "reason": "'field' required for 'hdel'"}
            count = await self.redis.hdel(key, field)
            return {"status": "success", "action": "hdel", "key": key, "deleted_count": count}

        # ------------------------------------------
        # List: lpush / rpush / lpop / lrange
        # payload 예시:
        #   lpush  → {action, key, value}
        #   rpush  → {action, key, value}
        #   lpop   → {action, key}
        #   lrange → {action, key, start, stop}  (stop=-1이면 전체)
        # ------------------------------------------
        elif action == "lpush":
            value = payload.get("value")
            if value is None:
                return {"status": "error", "reason": "'value' required for 'lpush'"}
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            length = await self.redis.lpush(key, str(value))
            return {"status": "success", "action": "lpush", "key": key, "length": length}

        elif action == "rpush":
            value = payload.get("value")
            if value is None:
                return {"status": "error", "reason": "'value' required for 'rpush'"}
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            length = await self.redis.rpush(key, str(value))
            return {"status": "success", "action": "rpush", "key": key, "length": length}

        elif action == "lpop":
            value = await self.redis.lpop(key)
            return {"status": "success", "action": "lpop", "key": key, "value": value}

        elif action == "lrange":
            start = payload.get("start", 0)
            stop  = payload.get("stop", -1)
            items = await self.redis.lrange(key, start, stop)
            return {"status": "success", "action": "lrange", "key": key, "data": items}

        # ------------------------------------------
        # Set: sadd / smembers / srem
        # payload 예시:
        #   sadd     → {action, key, member}
        #   smembers → {action, key}
        #   srem     → {action, key, member}
        # ------------------------------------------
        elif action == "sadd":
            member = payload.get("member")
            if member is None:
                return {"status": "error", "reason": "'member' required for 'sadd'"}
            count = await self.redis.sadd(key, str(member))
            return {"status": "success", "action": "sadd", "key": key, "added_count": count}

        elif action == "smembers":
            members = await self.redis.smembers(key)
            return {"status": "success", "action": "smembers", "key": key, "data": list(members)}

        elif action == "srem":
            member = payload.get("member")
            if member is None:
                return {"status": "error", "reason": "'member' required for 'srem'"}
            count = await self.redis.srem(key, str(member))
            return {"status": "success", "action": "srem", "key": key, "removed_count": count}

        # ------------------------------------------
        # TTL: expire / ttl
        # payload 예시:
        #   expire → {action, key, ttl}  (초 단위)
        #   ttl    → {action, key}
        # ------------------------------------------
        elif action == "expire":
            ttl = payload.get("ttl")
            if ttl is None:
                return {"status": "error", "reason": "'ttl' required for 'expire'"}
            await self.redis.expire(key, int(ttl))
            return {"status": "success", "action": "expire", "key": key, "ttl": ttl}

        elif action == "ttl":
            remaining = await self.redis.ttl(key)
            return {"status": "success", "action": "ttl", "key": key, "ttl": remaining}

        else:
            return {"status": "error", "reason": f"Unsupported action: '{action}'"}

    # =========================================================
    # 종료
    # =========================================================

    async def close(self):
        print("[RedisManager] 커넥션 풀 종료 및 자원 반환")
        await self.redis.aclose()
