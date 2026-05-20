import json
from typing import Any, Optional
# 실제 프로젝트 디렉토리 구조에 맞추어 import 경로를 수정해 주세요.
from module.node.base.base import BaseProcessor 
from module.node.memory.redis_manager import RedisManager

class RedisProcessorNode(BaseProcessor):
    def __init__(self, redis_manager_instance: RedisManager):
        super().__init__()
        # 주입받은 RedisManager 인스턴스를 저장합니다.
        self.redis_db = redis_manager_instance 

    async def on_start(self) -> None:
        # 노드 초기화 시점의 로그. 비동기 환경임을 명확히 인지할 수 있도록 출력합니다.
        print("[Redis Node] 노드가 시작되었습니다. 순수 비동기 Redis 매니저 연결 확인.")

    async def on_stop(self) -> None:
        print("[Redis Node] 노드 종료.")
        # 시스템 아키텍처에 따라 여기서 매니저의 커넥션을 닫을 수도 있으나,
        # 싱글톤 매니저는 보통 앱 생명주기(Lifespan) 최상단에서 통합 종료하는 것이 안전합니다.

    async def process(self, data: Any) -> Optional[Any]:
        # 1. 입력 데이터 검증 및 파싱 (기존 DB 노드와 완벽히 동일한 방어 로직)
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

        # 2. Redis 매니저에게 작업 위임 (Lock 우회 및 즉각적인 await 호출)
        # payload 예시: {"action": "set", "key": "refresh_token:123", "value": "xyz...", "ttl": 1209600}
        result = await self.redis_db.execute(payload)

        # 3. 에러 처리 및 시그널 전파
        if result.get("status") == "error":
            self.signal("error", result.get("reason"))
            return json.dumps({"status": "error", "reason": result.get("reason")})

        # 4. 성공 시 결과를 JSON 문자열로 직렬화하여 반환
        return json.dumps(result)