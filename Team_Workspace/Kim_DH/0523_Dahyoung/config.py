import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 0. 환경 변수 로드 (절대 경로 탐색 보장)
# ==========================================
CURRENT_DIR = Path(__file__).resolve().parent
ENV_PATH = CURRENT_DIR / ".env"
load_dotenv(ENV_PATH)

# 공통 기본 API 키
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==========================================
# 1. 대화 생성 에이전트 세트 (Generation)
# ==========================================
GENERATION_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_GENERATION = os.getenv("LLM_MODEL_GENERATION", "gpt-4o-mini")

# {p_topic}, {s_topic}, {s_context}, {past_chat_history}, {current_msg_content} 자리표시자 사용
GENERATION_PROMPT = (
    "[개인화 정보]: {p_topic}\n"
    "[현재 대화 주제]: {s_topic}\n"
    "[이전 대화 요약]: {s_context}\n"
    "[최근 대화 기록 (버퍼)]:\n{past_chat_history}\n"
    "[현재 사용자 메시지]: {current_msg_content}"
)

# ==========================================
# 라우터 전용 프롬프트 (Port3 → LLM)
# {usr_anal}, {ssn_tpc}, {ssn_pcl}, {cc} 자리표시자 사용
# 출력: LLM_Response JSON (protocol.py 스펙 그대로)
# ==========================================
ROUTER_PROMPT = (
    "너는 여행 계획 도우미 AI야.\n"
    "아래 정보를 참고해서 사용자 메시지에 답하고, 반드시 아래 JSON 형식으로만 출력해. 다른 말은 절대 쓰지 마.\n"
    "\n"
    "출력 형식:\n"
    "{{\n"
    '  "USR_ANAL": "<그대로 유지>",\n'
    '  "SSN_TPC":  "<그대로 유지>",\n'
    '  "SSN_PCL":  "<그대로 유지>",\n'
    '  "CC":   "<사용자에게 보여줄 답변 텍스트>",\n'
    '  "T_SL": "<선택지 문자열, 없으면 빈 문자열>",\n'
    '  "T_CD": ["YYMMDD", ...],\n'
    '  "T_MP": ["폴리곤 노드 ID", ...],\n'
    '  "T_MK": [{{"marker_id":"...","place_info":{{"name":"","address_road":"","lat":0.0,"lon":0.0,"description":"","category":""}}}}],\n'
    '  "T_PN": [[{{"date":"YYMMDD","order":0,"place":"장소명","place_info":{{"name":"","address_road":"","lat":0.0,"lon":0.0,"description":"","category":""}}}}]]\n'
    "}}\n"
    "\n"
    "T_SL 선택지 규칙:\n"
    "- 사용자의 목적이 명확하거나 단순 정보 질문이면 T_SL은 빈 문자열로 둔다.\n"
    "- 요청이 넓거나 추상적이거나, 조건이 부족해 임의 결정이 위험하거나, 좋은 방향이 2개 이상 가능하거나, 선호가 불명확하거나, 일정/동선/비용 트레이드오프가 있으면 A안/B안을 제시한다.\n"
    "- A안/B안을 제시할 때 CC에는 사용자가 고르도록 짧게 안내하고, T_SL은 반드시 'A안: 자연·관광 중심 | B안: 맛집·카페 중심' 형식의 짧은 선택지 문자열만 넣는다.\n"
    "- 구체적인 성향이 없으면 기본 축은 'A안: 자연·관광 중심 | B안: 맛집·카페 중심'으로 둔다.\n"
    "- 질문 성향이 명확하면 자연/관광 vs 맛집/카페, 동선 효율 vs 인기 장소, 여유로운 일정 vs 빡빡한 일정, 동부권 vs 서부권, 가족/힐링형 vs 활동/체험형 중 가장 맞는 축으로 나눈다.\n"
    "\n"
    "T_SL은 선택지가 없으면 빈 문자열로 둔다. T_CD/T_MP/T_MK/T_PN은 기존 라우터 규칙을 따른다.\n"
    "\n"
    "[개인화 정보]: {usr_anal}\n"
    "[현재 대화 주제]: {ssn_tpc}\n"
    "[과거 대화 기록]:\n{ssn_pcl}\n"
    "[현재 사용자 메시지]: {cc}"
)

# ==========================================
# 2. 맥락 흡수 에이전트 세트 (Absorb) — 버퍼 풀 때 topic+summary 통합
# ==========================================
ABSORB_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_ABSORB = os.getenv("LLM_MODEL_ABSORB", "gpt-4o-mini")

# {current_context}, {history_text} 자리표시자 사용
# 출력 형식: 첫 줄 "title: <15자 이내>", 둘째 줄 "context: <한 문단 100자 이내>"
ABSORB_PROMPT = (
    "너는 여행 대화 세션을 관리하는 AI야.\n"
    "기존 세션 주제와 요약, 새 대화를 통합하여 아래 형식으로만 응답해. 다른 말은 절대 쓰지 마.\n"
    "title: <갱신된 세션 주제 이름, 20자 이내>\n"
    "context: <봇이 앞으로 참고할 핵심 정보를 한 문단으로 100자 이내>\n"
    "[현재 세션 주제]: {current_title}\n"
    "[기존 대화 요약]: {current_context}\n"
    "[새로 추가된 대화 내역]:\n{history_text}"
)

# ==========================================
# 4. 개인화 정보 처리 에이전트 세트 (Personal)
# ==========================================
PERSONAL_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL_PERSONAL = os.getenv("LLM_MODEL_PERSONAL", "gpt-4o-mini")
# {prev_summary}, {delta_type}, {delta_description}, {session_topics},
# {travel_settings} 자리표시자 사용
PERSONAL_PROMPT = (
    "너는 여행 사용자 성향 분석 AI야.\n"
    "아래 정보를 종합하여 정확히 두 문단으로만 출력해. 다른 말은 쓰지 마.\n"
    "첫 번째 문단: 'AI 스타일 : '로 시작하여 AI가 이 사용자에게 어떤 말투·스타일로 응답해야 하는지 서술(200자 이내).\n"
    "두 번째 문단: '사용자 스타일 : '로 시작하여 사용자의 여행 성향·관심사·목적을 서술(300자 이내).\n"
    "[현재 분석 요약]: {prev_summary}\n"
    "[변화 유형]: {delta_type}\n"
    "[새로운 정보]: {delta_description}\n"
    "[보유 세션 주제 목록]: {session_topics}\n"
    "[AI 스타일 설정]: {style_settings}\n"
    "[여행 취향 설정]: {travel_settings}"
)

# ==========================================
# 5. 인증 설정 (JWT)
# ==========================================
ACCESS_TOKEN_SECRET_KEY = os.getenv("ACCESS_TOKEN_SECRET_KEY", "")
REFRESH_TOKEN_SECRET_KEY = os.getenv("REFRESH_TOKEN_SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
REFRESH_TOKEN_EXPIRE_DAYS = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")





#docker compose -f docker-compose-db.yml up -d && docker compose -f docker-compose-system.yml up -d --build && docker compose -f docker-compose-nginx.yml up -d
#docker rm -f travelarchive_nginx && docker rm -f travelarchive_backend && docker rm -f travelarchive_db
