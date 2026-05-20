"""
redis_tables.py

Redis에 저장되는 데이터 구조를 Python 클래스로 정의합니다.
노드 파이프라인과 무관하게, 백엔드 어디서든 직접 Redis 데이터를
읽고 쓸 수 있는 직접 접근 레이어입니다.

사용 예시:
    meta = SessionMeta(owner="MEM:abc", title="오사카", mode="personal")
    await meta.save(redis_manager, session_id="sess_123")

    meta = await SessionMeta.load(redis_manager, "sess_123")
    print(meta.title)

키 구조 (초안_0 기준):
    auth:refresh:{jti}          → AuthRefreshToken  (String)
    user:GST:{uuid}             → GuestUser         (Hash)
    session:{id}:meta           → SessionMeta       (Hash)
    session:{id}:state          → SessionState      (String)
    user:{user_id}:sessions     → UserSessions      (Set)
    queue:tasks                 → TaskQueue         (List)
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from module.node.memory.redis_manager import RedisManager

# =========================================================
# TTL 상수
# =========================================================

TTL_REFRESH_TOKEN = 7  * 24 * 3600   # 7일  (초 단위)
TTL_MEMBER        = 48 * 3600         # 48시간
TTL_GUEST         = 24 * 3600         # 24시간


# =========================================================
# AuthRefreshToken — auth:refresh:{jti}  [String]
# JWT Refresh Token 저장. 로그아웃 시 삭제하여 무효화.
# =========================================================

class AuthRefreshToken:
    KEY = "auth:refresh:{jti}"

    @staticmethod
    def _key(jti: str) -> str:
        return f"auth:refresh:{jti}"

    @staticmethod
    async def save(redis: RedisManager, jti: str, user_id: str, ttl: int = TTL_REFRESH_TOKEN):
        """Refresh Token 저장."""
        await redis.execute({
            "action": "set",
            "key": AuthRefreshToken._key(jti),
            "value": user_id,
            "ttl": ttl
        })

    @staticmethod
    async def load(redis: RedisManager, jti: str) -> Optional[str]:
        """user_id 반환. 만료됐거나 없으면 None."""
        result = await redis.execute({
            "action": "get",
            "key": AuthRefreshToken._key(jti)
        })
        return result.get("value")

    @staticmethod
    async def delete(redis: RedisManager, jti: str):
        """로그아웃 시 토큰 무효화."""
        await redis.execute({
            "action": "delete",
            "key": AuthRefreshToken._key(jti)
        })


# =========================================================
# GuestUser — user:GST:{uuid}  [Hash]
# 게스트 사용자 임시 정보. TTL 만료 시 자동 소멸.
# =========================================================

@dataclass
class GuestUser:
    uuid: str
    created_at: str = ""       # ISO 문자열
    session_id: str = ""       # 게스트는 세션 하나만

    @property
    def _key(self) -> str:
        return f"user:GST:{self.uuid}"

    async def save(self, redis: RedisManager, ttl: int = TTL_GUEST):
        await redis.execute({
            "action": "hset",
            "key": self._key,
            "mapping": {
                "uuid":       self.uuid,
                "created_at": self.created_at,
                "session_id": self.session_id,
            },
            "ttl": ttl
        })

    @classmethod
    async def load(cls, redis: RedisManager, uuid: str) -> Optional["GuestUser"]:
        result = await redis.execute({
            "action": "hgetall",
            "key": f"user:GST:{uuid}"
        })
        data = result.get("data", {})
        if not data:
            return None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    async def delete(self, redis: RedisManager):
        await redis.execute({"action": "delete", "key": self._key})


# =========================================================
# SessionMeta — session:{id}:meta  [Hash]
# 세션의 핵심 메타 정보. flush 시 PostgreSQL에 동기화.
# =========================================================

@dataclass
class SessionMeta:
    owner: str            # user_id (MEM:abc, GST:uuid 등)
    title: str = ""
    topic: str = ""
    context: str = ""
    mode: str = "personal"
    is_manual_title: str = "false"   # Redis는 string만 — "true"/"false"

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session:{session_id}:meta"

    async def save(self, redis: RedisManager, session_id: str, ttl: Optional[int] = None):
        """세션 메타 저장. ttl 미지정 시 user_type으로 자동 결정."""
        if ttl is None:
            ttl = TTL_GUEST if self.owner.startswith("GST") else TTL_MEMBER
        await redis.execute({
            "action": "hset",
            "key": self._key(session_id),
            "mapping": {
                "owner":           self.owner,
                "title":           self.title,
                "topic":           self.topic,
                "context":         self.context,
                "mode":            self.mode,
                "is_manual_title": self.is_manual_title,
            },
            "ttl": ttl
        })

    @classmethod
    async def load(cls, redis: RedisManager, session_id: str) -> Optional["SessionMeta"]:
        result = await redis.execute({
            "action": "hgetall",
            "key": cls._key(session_id)
        })
        data = result.get("data", {})
        if not data:
            return None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    async def update_field(self, redis: RedisManager, session_id: str, field: str, value: str):
        """단일 필드만 수정. 전체 재저장 없이 효율적으로."""
        await redis.execute({
            "action": "hset",
            "key": self._key(session_id),
            "field": field,
            "value": value
        })

    @staticmethod
    async def delete(redis: RedisManager, session_id: str):
        await redis.execute({"action": "delete", "key": SessionMeta._key(session_id)})


# =========================================================
# SessionState — session:{id}:state  [String]
# 현재 세션의 처리 상태. Worker가 읽고 쓰는 플래그.
# =========================================================

class SessionState:
    IDLE       = "idle"
    PROCESSING = "processing"
    ERROR      = "error"

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session:{session_id}:state"

    @staticmethod
    async def set(redis: RedisManager, session_id: str, state: str, ttl: Optional[int] = None):
        await redis.execute({
            "action": "set",
            "key": SessionState._key(session_id),
            "value": state,
            "ttl": ttl
        })

    @staticmethod
    async def get(redis: RedisManager, session_id: str) -> Optional[str]:
        result = await redis.execute({
            "action": "get",
            "key": SessionState._key(session_id)
        })
        return result.get("value")

    @staticmethod
    async def delete(redis: RedisManager, session_id: str):
        await redis.execute({"action": "delete", "key": SessionState._key(session_id)})


# =========================================================
# UserSessions — user:{user_id}:sessions  [Set]
# 사용자가 보유한 session_id 목록. 중복 없이 관리.
# =========================================================

class UserSessions:

    @staticmethod
    def _key(user_id: str) -> str:
        return f"user:{user_id}:sessions"

    @staticmethod
    async def add(redis: RedisManager, user_id: str, session_id: str):
        await redis.execute({
            "action": "sadd",
            "key": UserSessions._key(user_id),
            "member": session_id
        })

    @staticmethod
    async def get_all(redis: RedisManager, user_id: str) -> list:
        result = await redis.execute({
            "action": "smembers",
            "key": UserSessions._key(user_id)
        })
        return result.get("data", [])

    @staticmethod
    async def remove(redis: RedisManager, user_id: str, session_id: str):
        await redis.execute({
            "action": "srem",
            "key": UserSessions._key(user_id),
            "member": session_id
        })

    @staticmethod
    async def delete(redis: RedisManager, user_id: str):
        """사용자 탈퇴 또는 게스트 만료 시 전체 삭제."""
        await redis.execute({"action": "delete", "key": UserSessions._key(user_id)})


# =========================================================
# TaskQueue — queue:tasks  [List]
# 백엔드 Worker가 소비하는 작업 큐. LPUSH → LPOP 구조.
# =========================================================

@dataclass
class Task:
    task_id: str
    session_id: str
    user_id: str
    message: str
    status: str = "pending"   # pending / running / done / error

    def to_json(self) -> str:
        return json.dumps({
            "task_id":    self.task_id,
            "session_id": self.session_id,
            "user_id":    self.user_id,
            "message":    self.message,
            "status":     self.status,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Task":
        data = json.loads(raw)
        return cls(**data)


class TaskQueue:
    KEY = "queue:tasks"

    @staticmethod
    async def enqueue(redis: RedisManager, task: Task):
        """작업을 큐에 넣기 (오른쪽 삽입)."""
        await redis.execute({
            "action": "rpush",
            "key": TaskQueue.KEY,
            "value": task.to_json()
        })

    @staticmethod
    async def dequeue(redis: RedisManager) -> Optional[Task]:
        """큐에서 작업 꺼내기 (왼쪽 꺼내기). 큐가 비었으면 None."""
        result = await redis.execute({
            "action": "lpop",
            "key": TaskQueue.KEY
        })
        raw = result.get("value")
        if raw is None:
            return None
        return Task.from_json(raw)

    @staticmethod
    async def peek_all(redis: RedisManager) -> list:
        """큐 전체를 꺼내지 않고 확인만 (어드민/디버깅용)."""
        result = await redis.execute({
            "action": "lrange",
            "key": TaskQueue.KEY,
            "start": 0,
            "stop": -1
        })
        return [Task.from_json(raw) for raw in result.get("data", [])]
