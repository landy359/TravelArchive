import os
import sys
import asyncio
import json
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# .env 로드
load_dotenv(PROJECT_ROOT / "setting" / ".env")

# Redis는 6379이 호스트에 노출되어 있으므로 localhost 직접 사용
_pw = quote(os.getenv("REDIS_PASSWORD", ""), safe="")
_db = os.getenv("REDIS_DB_INDEX", "0")
os.environ["REDIS_URL"] = f"redis://:{_pw}@localhost:6379/{_db}"

from module.node.memory.redis_manager import RedisManager
from module.node.memory.redis_node import RedisProcessorNode

# =========================================================
# 테스트용 키 네임스페이스 (실제 서비스 키와 충돌 방지)
# =========================================================
USER_ID    = "test_user_001"
SESSION_A  = "test_sess_A"
SESSION_B  = "test_sess_B"
QUEUE_KEY  = "queue:test_tasks"   # 이 키는 마지막에 삭제


# =========================================================
# Node 1 — session_node: Hash / String / Set 담당
# 데이터는 DB에 남김
# =========================================================

async def session_worker(node: RedisProcessorNode):
    print("\n[Session Node] ── 세션 2개 생성 ──────────────────")

    # ── 세션 A ──────────────────────────────────────────
    await node.process({
        "action": "hset",
        "key": f"session:{SESSION_A}:meta",
        "mapping": {
            "owner":           USER_ID,
            "title":           "도쿄 여행 계획",
            "topic":           "일본 도쿄 3박4일",
            "context":         "첫 해외여행, 예산 100만원",
            "mode":            "personal",
            "is_manual_title": "true",
        },
        "ttl": 3600
    })
    await node.process({
        "action": "set",
        "key": f"session:{SESSION_A}:state",
        "value": "idle",
        "ttl": 3600
    })
    print(f"  [Session Node] {SESSION_A} 생성 완료")

    # ── 세션 B ──────────────────────────────────────────
    await node.process({
        "action": "hset",
        "key": f"session:{SESSION_B}:meta",
        "mapping": {
            "owner":           USER_ID,
            "title":           "제주도 드라이브",
            "topic":           "제주 렌터카 여행",
            "context":         "친구 3명, 2박3일",
            "mode":            "team",
            "is_manual_title": "false",
        },
        "ttl": 3600
    })
    await node.process({
        "action": "set",
        "key": f"session:{SESSION_B}:state",
        "value": "processing",
        "ttl": 3600
    })
    print(f"  [Session Node] {SESSION_B} 생성 완료")

    # ── 유저 세션 목록(Set)에 등록 ────────────────────────
    for sid in [SESSION_A, SESSION_B]:
        await node.process({
            "action": "sadd",
            "key": f"user:{USER_ID}:sessions",
            "member": sid
        })
    print(f"  [Session Node] user:{USER_ID}:sessions 에 2개 등록")

    # ── 세션 A 상태를 processing으로 업데이트 ─────────────
    await node.process({
        "action": "set",
        "key": f"session:{SESSION_A}:state",
        "value": "processing"
    })
    print(f"  [Session Node] {SESSION_A} state → processing")

    # ── 조회 ────────────────────────────────────────────
    print("\n[Session Node] ── 조회 ────────────────────────────")

    result = await node.process({"action": "hgetall", "key": f"session:{SESSION_A}:meta"})
    print(f"  META  {SESSION_A}: {json.loads(result)['data']}")

    result = await node.process({"action": "get", "key": f"session:{SESSION_A}:state"})
    print(f"  STATE {SESSION_A}: {json.loads(result)['value']}")

    result = await node.process({"action": "hgetall", "key": f"session:{SESSION_B}:meta"})
    print(f"  META  {SESSION_B}: {json.loads(result)['data']}")

    result = await node.process({"action": "get", "key": f"session:{SESSION_B}:state"})
    print(f"  STATE {SESSION_B}: {json.loads(result)['value']}")

    result = await node.process({"action": "smembers", "key": f"user:{USER_ID}:sessions"})
    print(f"  SESSIONS of {USER_ID}: {json.loads(result)['data']}")

    # ── TTL 확인 ─────────────────────────────────────────
    result = await node.process({"action": "ttl", "key": f"session:{SESSION_A}:meta"})
    print(f"  TTL   {SESSION_A}:meta → {json.loads(result)['ttl']}초 남음")


# =========================================================
# Node 2 — task_node: List(Queue) 담당
# 마지막에 queue:test_tasks 키 삭제
# =========================================================

async def task_worker(node: RedisProcessorNode):
    print("\n[Task Node] ── 작업 큐 테스트 ─────────────────────")

    tasks = [
        {"task_id": "t001", "session_id": SESSION_A, "user_id": USER_ID, "message": "도쿄 맛집 추천해줘", "status": "pending"},
        {"task_id": "t002", "session_id": SESSION_A, "user_id": USER_ID, "message": "신주쿠 호텔 알아봐줘", "status": "pending"},
        {"task_id": "t003", "session_id": SESSION_B, "user_id": USER_ID, "message": "제주 렌터카 업체 비교", "status": "pending"},
    ]

    # 큐에 RPUSH (enqueue)
    for t in tasks:
        result = await node.process({"action": "rpush", "key": QUEUE_KEY, "value": t})
        print(f"  [Task Node] ENQUEUE → task_id={t['task_id']} (queue length={json.loads(result)['length']})")

    # 큐 전체 확인 (꺼내지 않고)
    result = await node.process({"action": "lrange", "key": QUEUE_KEY, "start": 0, "stop": -1})
    items = json.loads(result)["data"]
    print(f"\n  [Task Node] 큐 peek (전체 {len(items)}건):")
    for raw in items:
        t = json.loads(raw)
        print(f"    → {t['task_id']} | {t['message']}")

    # LPOP으로 작업 1건 소비
    result = await node.process({"action": "lpop", "key": QUEUE_KEY})
    consumed = json.loads(json.loads(result)["value"])
    print(f"\n  [Task Node] DEQUEUE (소비) → {consumed['task_id']}: {consumed['message']}")

    # 남은 큐 확인
    result = await node.process({"action": "lrange", "key": QUEUE_KEY, "start": 0, "stop": -1})
    remaining = json.loads(result)["data"]
    print(f"  [Task Node] 남은 큐: {len(remaining)}건")

    # 큐 키 삭제 (test_tasks만 제거)
    result = await node.process({"action": "delete", "key": QUEUE_KEY})
    print(f"\n  [Task Node] '{QUEUE_KEY}' 삭제 완료 (deleted_count={json.loads(result)['deleted_count']})")


# =========================================================
# 메인
# =========================================================

async def main():
    redis_url = os.getenv("REDIS_URL")
    print(f"[INFO] REDIS_URL: {redis_url}\n")

    # ── 매니저 1개, 노드 2개 ──────────────────────────────
    manager = RedisManager(redis_url=redis_url)

    session_node = RedisProcessorNode(redis_manager_instance=manager)
    task_node    = RedisProcessorNode(redis_manager_instance=manager)

    await session_node.on_start()
    await task_node.on_start()

    print("=" * 55)
    print("  Phase 1: 두 노드 병렬 실행 (asyncio.gather)")
    print("=" * 55)

    await asyncio.gather(
        session_worker(session_node),
        task_worker(task_node)
    )

    print("\n" + "=" * 55)
    print("  Phase 2: 최종 키 상태 확인")
    print("=" * 55)

    keys_to_check = [
        f"session:{SESSION_A}:meta",
        f"session:{SESSION_A}:state",
        f"session:{SESSION_B}:meta",
        f"session:{SESSION_B}:state",
        f"user:{USER_ID}:sessions",
        QUEUE_KEY,
    ]
    for key in keys_to_check:
        result = await session_node.process({"action": "exists", "key": key})
        exists = json.loads(result)["exists"]
        print(f"  {'✔ 존재' if exists else '✘ 없음'} → {key}")

    await session_node.on_stop()
    await task_node.on_stop()
    await manager.close()

    print("\n[DONE] 테스트 완료.")
    print("  session / user 키는 DB에 남아 있습니다. RedisInsight(5540포트)로 확인 가능.")
    print(f"  삭제된 키: {QUEUE_KEY}")


if __name__ == "__main__":
    asyncio.run(main())
