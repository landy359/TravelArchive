"""
회원가입 로직 디버깅 스크립트
직접 DB에 접근해서 각 단계가 제대로 작동하는지 확인
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
import uuid

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from module.node.memory.postgres_manager import PostgresManager
from module.node.memory.postgres_tables import User, UserProfile, UserSecurity, UserPreference, Base
from backend.auth.password_utils import hash_password

async def test_signup():
    # DB 매니저 초기화
    postgres = PostgresManager()
    
    # 모델 등록
    postgres.register_model("User", User)
    postgres.register_model("UserProfile", UserProfile)
    postgres.register_model("UserSecurity", UserSecurity)
    postgres.register_model("UserPreference", UserPreference)
    
    print("[Test] 모델 등록 완료")
    
    # 테이블 생성
    postgres.create_tables(Base.metadata)
    print("[Test] 테이블 생성 완료")
    
    # 테스트 데이터
    email = "test@example.com"
    password = "password123"
    nickname = "테스트유저"
    user_id = "MEM:" + str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    
    print(f"\n[Test] 테스트 시작: user_id={user_id}, email={email}")
    
    # Step 1: User 테이블에 insert
    result = await postgres.execute({
        "action": "create",
        "model": "User",
        "data": {
            "user_id": user_id,
            "user_type": "MEM",
            "status": "active",
            "created_at": now
        }
    })
    print(f"[Step 1] User insert: {result}")
    
    # Step 2: UserProfile 테이블에 insert
    result = await postgres.execute({
        "action": "create",
        "model": "UserProfile",
        "data": {
            "user_id": user_id,
            "email": email,
            "nickname": nickname,
            "updated_at": now
        }
    })
    print(f"[Step 2] UserProfile insert: {result}")
    
    # Step 3: UserSecurity 테이블에 insert
    result = await postgres.execute({
        "action": "create",
        "model": "UserSecurity",
        "data": {
            "user_id": user_id,
            "password_hash": hash_password(password),
            "login_fail_count": 0
        }
    })
    print(f"[Step 3] UserSecurity insert: {result}")
    
    # Step 4: UserPreference 테이블에 insert
    result = await postgres.execute({
        "action": "create",
        "model": "UserPreference",
        "data": {
            "user_id": user_id,
            "updated_at": now
        }
    })
    print(f"[Step 4] UserPreference insert: {result}")
    
    # Step 5: 이메일로 조회
    print(f"\n[Step 5] 이메일로 조회 시작: {email}")
    result = await postgres.execute({
        "action": "read",
        "model": "UserProfile",
        "filters": {"email": email}
    })
    print(f"[Step 5] UserProfile read by email: {result}")
    
    # Step 6: user_id로 조회
    print(f"\n[Step 6] user_id로 조회 시작: {user_id}")
    result = await postgres.execute({
        "action": "read",
        "model": "UserProfile",
        "filters": {"user_id": user_id}
    })
    print(f"[Step 6] UserProfile read by user_id: {result}")
    
    # Step 7: 모든 User 조회
    print(f"\n[Step 7] 모든 User 조회")
    result = await postgres.execute({
        "action": "read",
        "model": "User"
    })
    print(f"[Step 7] All Users: {result}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, "setting", ".env"))
    
    asyncio.run(test_signup())
