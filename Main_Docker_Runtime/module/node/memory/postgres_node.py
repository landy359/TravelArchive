import json
from typing import Any, Optional

from module.node.base.base import BaseProcessor
from module.node.memory.postgres_manager import PostgresManager


class PostgresProcessorNode(BaseProcessor):
    def __init__(self, postgres_manager_instance: PostgresManager):
        super().__init__()
        self.db = postgres_manager_instance

    async def on_start(self) -> None:
        print("[Postgres Node] 노드가 시작되었습니다. PostgresManager 연결 확인.")

    async def on_stop(self) -> None:
        print("[Postgres Node] 노드 종료.")

    async def process(self, data: Any) -> Optional[Any]:
        if isinstance(data, str):
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                self.signal("error", "Invalid JSON string")
                return json.dumps({"status": "error", "reason": "Invalid JSON string"})
        elif isinstance(data, dict):
            payload = data
        else:
            self.signal("error", "Unsupported data type")
            return json.dumps({"status": "error", "reason": "Unsupported data type"})

        result = await self.db.execute(payload)

        if result.get("status") == "error":
            self.signal("error", result.get("reason"))
            return json.dumps({"status": "error", "reason": result.get("reason")})

        return json.dumps(result)
