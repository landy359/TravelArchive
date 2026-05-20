import os
import sys
import asyncio
import json
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# .env 로드
load_dotenv(PROJECT_ROOT / "setting" / ".env")

_user = os.getenv("POSTGRES_USER", "TravelArchiveAdmin")
_pass = quote_plus(os.getenv("POSTGRES_PASS", ""))
_db   = os.getenv("POSTGRES_DB", "travelarchive")
_port = os.getenv("DB_PORT", "5432")
os.environ["DATABASE_URL"] = f"postgresql://{_user}:{_pass}@172.19.0.6:{_port}/{_db}"

from module.node.memory.postgres_manager import PostgresManager
from module.node.memory.postgres_node import PostgresProcessorNode

# =========================================================
# 테스트용 테이블 2개 정의 (공통 Base)
# =========================================================

TestBase = declarative_base()


class TestArticle(TestBase):
    """게시글 테이블"""
    __tablename__ = "test_article"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    title      = Column(String(100), nullable=False)
    body       = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class TestComment(TestBase):
    """댓글 테이블 — article_id로 게시글 참조"""
    __tablename__ = "test_comment"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, nullable=False)   # 테스트용이므로 FK 없이 단순 참조
    author     = Column(String(50), nullable=False)
    text       = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# =========================================================
# 동시 작업 함수
# =========================================================

async def article_worker(node: PostgresProcessorNode):
    """게시글 노드: CREATE 3건 → READ"""
    print("\n[Article Node] 게시글 3건 삽입 시작")
    for i in range(1, 4):
        result = await node.process({
            "action": "create",
            "model": "TestArticle",
            "data": {"title": f"게시글 {i}", "body": f"게시글 {i}의 본문입니다."}
        })
        data = json.loads(result).get("data", {})
        print(f"  [Article] CREATE → id={data.get('id')}, title={data.get('title')}")
        await asyncio.sleep(0.05)   # 댓글 노드와 번갈아 실행되도록 양보

    result = await node.process({"action": "read", "model": "TestArticle", "filters": {}})
    rows = json.loads(result).get("data", [])
    print(f"  [Article] READ 전체 → {len(rows)}건")
    return rows


async def comment_worker(node: PostgresProcessorNode, article_ids: list):
    """댓글 노드: 각 게시글에 댓글 2건씩 CREATE → READ"""
    print("\n[Comment Node] 댓글 삽입 시작")
    for aid in article_ids:
        for j in range(1, 3):
            result = await node.process({
                "action": "create",
                "model": "TestComment",
                "data": {
                    "article_id": aid,
                    "author": f"user_{aid}_{j}",
                    "text": f"게시글 {aid}에 달린 {j}번째 댓글"
                }
            })
            data = json.loads(result).get("data", {})
            print(f"  [Comment] CREATE → id={data.get('id')}, article_id={data.get('article_id')}, author={data.get('author')}")
            await asyncio.sleep(0.03)


async def main():
    db_url = os.getenv("DATABASE_URL")
    print(f"[INFO] DATABASE_URL: {db_url}\n")

    # ── 매니저 1개, 노드 2개 ──────────────────────────────
    manager = PostgresManager(db_url=db_url)
    manager.create_tables(TestBase.metadata)
    manager.register_model("TestArticle", TestArticle)
    manager.register_model("TestComment", TestComment)

    article_node = PostgresProcessorNode(postgres_manager_instance=manager)
    comment_node = PostgresProcessorNode(postgres_manager_instance=manager)
    await article_node.on_start()
    await comment_node.on_start()

    print("=" * 55)
    print("  Phase 1: 두 노드 동시 실행 (asyncio.gather)")
    print("=" * 55)

    # 게시글 3건을 먼저 만들어 ID를 얻은 뒤 댓글 작업을 함께 띄운다
    # article_worker가 CREATE를 마칠 때까지 댓글은 잠시 대기
    article_task  = asyncio.create_task(article_worker(article_node))

    # 게시글 CREATE가 완료될 때까지 댓글 노드는 대기 후 병렬 실행
    article_rows  = await article_task
    article_ids   = [row["id"] for row in article_rows]

    comment_task  = asyncio.create_task(comment_worker(comment_node, article_ids))
    await comment_task

    print("\n" + "=" * 55)
    print("  Phase 2: 두 노드 완전 병렬 (asyncio.gather)")
    print("=" * 55)
    # 게시글 추가 2건 + 댓글 추가를 동시에 쏜다 → 매니저 직렬화 확인
    async def add_more_articles():
        for i in range(4, 6):
            result = await article_node.process({
                "action": "create",
                "model": "TestArticle",
                "data": {"title": f"게시글 {i} (병렬)", "body": f"병렬 삽입 테스트 {i}"}
            })
            data = json.loads(result).get("data", {})
            print(f"  [Article/병렬] CREATE → id={data.get('id')}, title={data.get('title')}")

    async def add_more_comments():
        for aid in article_ids[:2]:
            result = await comment_node.process({
                "action": "create",
                "model": "TestComment",
                "data": {"article_id": aid, "author": "parallel_user", "text": f"병렬 댓글 on article {aid}"}
            })
            data = json.loads(result).get("data", {})
            print(f"  [Comment/병렬] CREATE → id={data.get('id')}, article_id={data.get('article_id')}")

    await asyncio.gather(add_more_articles(), add_more_comments())

    print("\n" + "=" * 55)
    print("  Phase 3: 최종 DB 상태 확인")
    print("=" * 55)

    article_result = await article_node.process({"action": "read", "model": "TestArticle", "filters": {}})
    comment_result = await comment_node.process({"action": "read", "model": "TestComment",  "filters": {}})

    articles = json.loads(article_result).get("data", [])
    comments = json.loads(comment_result).get("data", [])

    print(f"\n  [test_article] 총 {len(articles)}건")
    for a in articles:
        print(f"    id={a['id']} | {a['title']} | {a['created_at']}")

    print(f"\n  [test_comment] 총 {len(comments)}건")
    for c in comments:
        print(f"    id={c['id']} | article_id={c['article_id']} | {c['author']} | {c['text']}")

    await article_node.on_stop()
    await comment_node.on_stop()

    print("\n[DONE] 테스트 완료. DB에 데이터가 남아 있습니다.")
    print("  확인: docker exec -e PGPASSWORD='CWiS5oUjMLMrMNSNSawRDRFbQS74xOJG' TA_db psql -h 172.19.0.6 -U TravelArchiveAdmin -d travelarchive -c 'SELECT * FROM test_article; SELECT * FROM test_comment;'")


if __name__ == "__main__":
    asyncio.run(main())
