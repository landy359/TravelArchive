import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .adapters import MapNode, PgAdapter, RedisAdapter, TripRangeNode
from .manager import EventHandler


@asynccontextmanager
async def loader_lifespan(app: FastAPI) -> AsyncIterator[None]:
    pg_adapter = PgAdapter(os.environ["DATABASE_URL"])
    redis_adapter = RedisAdapter(os.environ["REDIS_URL"])
    map_node = MapNode()
    trip_range_node = TripRangeNode()
    map_node.bind_redis(redis_adapter)
    trip_range_node.bind_redis(redis_adapter)

    manager = EventHandler()
    await manager.start(pg_adapter, redis_adapter)

    app.state.postgres = pg_adapter
    app.state.redis = redis_adapter
    app.state.manager = manager
    app.state.map_node = map_node
    app.state.trip_range_node = trip_range_node

    print("[Loader] PostgreSQL & Redis 초기화 완료")
    try:
        yield
    finally:
        await manager.stop()
        await redis_adapter.close()
        pg_adapter.close()
        print("[Loader] 앱 종료 완료")
tokens used
51,244