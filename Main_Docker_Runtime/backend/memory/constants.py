# [역할] 메모리 계층 전역 상수 단일 출처.
#        TTL 값은 이 파일에서만 정의하고 모든 모듈이 여기서 import한다.

SESSION_TTL          = 3600 * 8    # 세션 메타·버퍼 — 8시간
USER_SESSION_SET_TTL = 3600 * 24   # 활성 세션 Set — 24시간
DATA_TTL             = 3600 * 24   # 위젯 데이터 (markers/routes/ranges) — 24시간
USER_DATA_TTL        = 3600 * 8    # 사용자 프로필·설정 — 8시간
USER_ANALYSIS_TTL    = 3600 * 24 * 7  # 성향 분석 — 7일

# MapNode / TripRangeNode 인메모리 버퍼 최대 세션 수
# 초과 시 LRU 방식으로 가장 오래된 세션을 제거한다.
MAX_BUFFER_SESSIONS  = 500
