# [역할] 여행(Trip) CRUD 전담. Cacher만 호출 — Redis 미러링만 본다.
#        모든 PG mutation은 manager(EventHandler)가 위임 처리한다.
#
#        호출 방향: SystemUnit → TripService → Cacher → (manager) → EventHandler → Loader
from typing import Any

from ...memory.cacher import Cacher


class TripService:

    @staticmethod
    async def get_trip_list(redis: Any, manager: Any, user_id: str) -> list:
        return await Cacher.get_trip_list(user_id, redis, manager)

    @staticmethod
    async def create_trip(redis: Any, manager: Any, user_id: str, data: dict) -> dict:
        return await Cacher.create_trip(user_id, data, redis, manager)

    @staticmethod
    async def update_trip(redis: Any, manager: Any, trip_id: str, user_id: str, data: dict) -> dict:
        return await Cacher.update_trip(trip_id, user_id, data, redis, manager)

    @staticmethod
    async def delete_trip(redis: Any, manager: Any, trip_id: str, user_id: str) -> dict:
        return await Cacher.delete_trip(trip_id, user_id, redis, manager)
